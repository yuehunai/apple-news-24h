import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('replay_compare', Path(__file__).with_name('replay_compare.py'))
replay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = replay
SPEC.loader.exec_module(replay)


class ReplayBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = replay.load_code(Path(__file__).resolve().parents[1])

    def test_unknown_and_exhausted_requests_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cache').mkdir()
            replay.save(root / 'cache/a.json', {'url': 'https://example.com/', 'status': 200, 'text': 'saved'})
            responses = replay.Responses(root, self.module)
            diagnostics = {}
            self.assertEqual(responses.fetch('https://example.com/', root / 'output', diagnostics), 'saved')
            for url in ['https://example.com/', 'https://unknown.example/']:
                with self.subTest(url=url), self.assertRaises(replay.ReplayViolation):
                    responses.fetch(url, root / 'output', diagnostics)
            self.assertFalse(responses.complete)
            self.assertEqual(diagnostics, {})

    def test_recorded_failures_then_separate_recovery_follow_call_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cache').mkdir()
            url = 'https://example.com/'
            replay.save(root / 'cache/a.json', {'url': url, 'status': 200, 'text': 'saved'})
            replay.save(root / 'requests.json', [
                {'url': url, 'sequence': 0, 'error': 'timeout'},
                {'url': url, 'sequence': 1, 'error': 'timeout'},
                {'url': url, 'sequence': 2, 'status': 200}])
            responses = replay.Responses(root, self.module)
            diagnostics = {}
            self.assertIsNone(responses.fetch(url, root / 'output', diagnostics, retries=1))
            self.assertEqual(diagnostics['failed_fetches'], [{'url': url, 'error': 'timeout'}])
            self.assertEqual(responses.fetch(url, root / 'output', diagnostics, retries=0), 'saved')
            self.assertEqual(responses.report()['unused_attempts'], {})

    def test_output_alias_cannot_overlap_evidence_or_old_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / 'evidence'
            evidence.mkdir()
            alias = root / 'alias'
            alias.symlink_to(evidence, target_is_directory=True)
            for output in [evidence, evidence / 'cache', root, alias / 'cache']:
                with self.subTest(output=output), self.assertRaises(ValueError):
                    replay.checked_paths(evidence, output)
            old = root / 'old'
            old.mkdir()
            (old / 'latest.json').write_text('{}')
            with self.assertRaises(ValueError):
                replay.checked_paths(evidence, old)


class AdditiveEvidenceComparisonTests(unittest.TestCase):
    def test_legacy_fact_or_category_change_is_not_normalized(self):
        baseline = {'articles': [], 'event_partitions': [], 'result': {'events': [
            {'category': 'hardware_products', 'key_facts': ['Original fact'], 'sources': []}], 'deferred_events': []}}
        changed = json.loads(json.dumps(baseline))
        changed['result']['events'][0]['key_facts'] = ['Changed fact']
        self.assertNotEqual(replay.separate_evidence(baseline)[0], replay.separate_evidence(changed)[0])
        changed['result']['events'][0]['key_facts'] = ['Original fact']
        changed['result']['events'][0]['category'] = 'software_systems'
        self.assertNotEqual(replay.separate_evidence(baseline)[0], replay.separate_evidence(changed)[0])

    def test_cross_article_evidence_reference_is_rejected(self):
        module = replay.load_code(Path(__file__).resolve().parents[1])
        evidence = module.capture_article_evidence('Source', 'https://example.com/original', '<p>Original fact</p>', 'Title')
        baseline = {'articles': [], 'event_partitions': [], 'result': {
            'source_evidence': {evidence.article_id: replay.plain(evidence)},
            'events': [{'sources': [{'name': 'Source', 'url': 'https://example.com/different', 'evidence_id': evidence.article_id}]}],
            'deferred_events': []}}
        with self.assertRaisesRegex(ValueError, 'different article'):
            replay.separate_evidence(baseline)


class TransportBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = replay.load_code(Path(__file__).resolve().parents[1])

    def response(self, raw, content_type):
        result = io.BytesIO(raw)
        result.headers = {'content-type': content_type}
        result.status = 200
        return result

    def test_real_fetch_retries_decodes_and_writes_success_cache(self):
        # Only urlopen and sleep are replaced; fetch_url and decode_response execute.
        for encoding in ['utf-8', 'gb18030']:
            for charset_location in ['http', 'html']:
                with self.subTest(encoding=encoding, charset_location=charset_location):
                    html = '苹果新闻' if charset_location == 'http' else f'<meta charset="{encoding}">苹果新闻'
                    content_type = f'text/html; charset={encoding}' if charset_location == 'http' else 'text/html'
                    with tempfile.TemporaryDirectory() as directory:
                        cache = Path(directory)
                        diagnostics = {}
                        with patch('urllib.request.urlopen', side_effect=[OSError('transient'), self.response(html.encode(encoding), content_type)]) as open_url, patch.object(self.module.time, 'sleep'):
                            result = self.module.fetch_url('https://example.com/', cache, diagnostics, retries=1)
                        self.assertEqual(result, html)
                        self.assertEqual(open_url.call_count, 2)
                        self.assertEqual(diagnostics, {})
                        saved = json.loads(next(cache.glob('*.json')).read_text())
                        self.assertEqual(saved['text'], html)
                        self.assertEqual(saved['url'], 'https://example.com/')
                        self.assertEqual(saved['status'], 200)

    def test_real_fetch_retry_exhaustion_reports_failure_without_success_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            diagnostics = {}
            with patch('urllib.request.urlopen', side_effect=OSError('offline')) as open_url, patch.object(self.module.time, 'sleep'):
                self.assertIsNone(self.module.fetch_url('https://example.com/', cache, diagnostics, retries=1))
            self.assertEqual(open_url.call_count, 2)
            self.assertEqual(diagnostics['failed_fetches'], [{'url': 'https://example.com/', 'error': 'OSError: offline'}])
            self.assertEqual(list(cache.glob('*.json')), [])

class LiveEntryTests(unittest.TestCase):
    def test_live_worker_uses_real_main_and_writes_both_outputs(self):
        from types import SimpleNamespace
        module = replay.load_code(Path(__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'live'
            args = SimpleNamespace(scope='live', evidence=None, output=output,
                baseline=Path(__file__).resolve().parents[1], at='2026-09-20T03:00:00+00:00',
                postprocess_repeat=3)
            with patch.object(replay, 'load_code', return_value=module), patch.object(module,
                    'collect_candidates_from_sources', return_value=[]), patch.object(module,
                    'main', wraps=module.main) as main, patch('urllib.request.urlopen',
                    side_effect=AssertionError('test must not use network')), patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(replay.worker(args), 0)
            self.assertEqual(main.call_count, 1)
            self.assertTrue((output / 'latest.json').exists())
            self.assertTrue((output / 'latest.brief.md').exists())
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['scope'], 'live')
            self.assertEqual(manifest['at'], args.at)
            timing = json.loads((output / 'timing.json').read_text())
            self.assertEqual(len(timing['postprocess']), 3)
            self.assertEqual(set(timing['stages']), {'collection', 'article_processing', 'event_processing', 'output'})

    def test_live_rejects_old_evidence_and_offline_worker_remains_network_closed(self):
        from types import SimpleNamespace
        code_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = ['replay_compare.py', '--scope', 'live', '--baseline', str(code_root),
                    '--candidate', str(code_root), '--at', '2026-09-20T03:00:00+00:00', '--output', str(root/'live')]
            for option in ('--evidence', '--baseline-artifact'):
                with self.subTest(option=option), patch.object(sys, 'argv', base+[option,str(root)]), patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
                    replay.main()
                self.assertEqual(error.exception.code, 2)
            evidence=root/'evidence';(evidence/'cache').mkdir(parents=True)
            module=replay.load_code(code_root)
            def accidental_network(*a, **k):
                import urllib.request
                return urllib.request.urlopen('https://example.invalid/')
            args=SimpleNamespace(scope='full',evidence=evidence,output=root/'offline',baseline=code_root,
                at='2026-09-20T03:00:00+00:00',postprocess_repeat=0)
            with patch.object(replay,'load_code',return_value=module), patch.object(module,
                    'collect_candidates_from_sources',side_effect=accidental_network):
                self.assertEqual(replay.worker(args),2)
            failure=json.loads((root/'offline/failure.json').read_text())
            self.assertIn('Network is forbidden',failure['error'])
            self.assertFalse((root/'offline/latest.json').exists())

    def test_same_live_input_compares_equal_across_output_paths_without_hiding_facts(self):
        from types import SimpleNamespace
        code_root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            outputs=[]
            for label in ('baseline','candidate'):
                module=replay.load_code(code_root)
                output=Path(directory)/label
                args=SimpleNamespace(scope='live',evidence=None,output=output,baseline=code_root,
                    at='2026-09-20T03:00:00+00:00',postprocess_repeat=0)
                with patch.object(replay,'load_code',return_value=module), patch.object(module,
                        'collect_candidates_from_sources',return_value=[]), patch('sys.stdout',new_callable=io.StringIO):
                    self.assertEqual(replay.worker(args),0)
                actual=json.loads((output/'latest.json').read_text())
                self.assertEqual(actual['brief_output'],str((output/'latest.brief.md').resolve()))
                outputs.append(json.loads((output/'behavior.json').read_text()))
            self.assertEqual(outputs[0],outputs[1])
            outputs[1]['result']['events'].append({'title':'A real changed action','sources':[]})
            self.assertNotEqual(replay.separate_evidence(outputs[0])[0],replay.separate_evidence(outputs[1])[0])

    def test_terminating_live_parent_reaps_both_real_workers_and_releases_locks(self):
        import os,signal,subprocess,select
        parent_code = r"""
import sys,json,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
from test_replay_compare import replay,MainResourceLifecycleTests
root=Path(sys.argv[2]);tests_path=str(Path(sys.argv[1]).resolve());original=subprocess.Popen;children=[]
def start(command,**kwargs):
    output=Path(command[command.index('--output')+1]);output.mkdir(parents=True,exist_ok=True)
    child=original([sys.executable,'-c',MainResourceLifecycleTests.CHILD,tests_path,'network',str(output/'cache'),str(output/'latest.json')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=kwargs['stderr'],text=True)
    assert child.stdout.readline().strip()=='READY'
    children.append({'pid':child.pid,'output':str(output)})
    (root/'children.json').write_text(json.dumps(children))
    if len(children)==2:print('READY',flush=True)
    return child
argv=['replay_compare.py','--scope','live','--baseline',str(root/'old'),'--candidate',str(root/'new'),'--at','2026-09-20T03:00:00+00:00','--output',str(root/'run')]
with patch.object(sys,'argv',argv),patch.object(replay.subprocess,'Popen',start):
    raise SystemExit(replay.main())
"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);children=[]
            parent=subprocess.Popen([sys.executable,'-c',parent_code,str(Path(__file__).resolve().parent),directory],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertTrue(select.select([parent.stdout],[],[],15)[0])
                self.assertEqual(parent.stdout.readline().strip(),'READY')
                children=json.loads((root/'children.json').read_text())
                self.assertEqual(len(children),2)
                parent.terminate();out,err=parent.communicate(timeout=15)
                self.assertEqual(parent.returncode,128 + signal.SIGTERM,(out,err))
                report=json.loads((root/'run/comparison.json').read_text())
                self.assertTrue(report['interrupted'])
                self.assertEqual(set(report['exit_codes']),{'baseline','candidate'})
                self.assertTrue(all(code < 0 for code in report['exit_codes'].values()))
                for child in children:
                    with self.assertRaises(ProcessLookupError):os.kill(child['pid'],0)
                    output=Path(child['output'])
                    module=replay.load_code(Path(__file__).resolve().parents[1])
                    with module.collection.run_resource_locks(output/'cache',(output/'latest.json',output/'latest.brief.md')):
                        pass
            finally:
                if parent.poll() is None:parent.kill();parent.communicate(timeout=15)
                for child in children:
                    try:os.kill(child['pid'],signal.SIGTERM)
                    except ProcessLookupError:pass

    def test_live_parent_starts_both_workers_before_waiting_and_retains_codes(self):
        launched = []
        class Child:
            def __init__(self, command, **kwargs):
                self.command = command
                launched.append(self)
            def poll(self):
                return 0
            def wait(self):
                assert len(launched) == 2, 'workers were serialized'
                return 2 if 'baseline' == Path(self.command[self.command.index('--output') + 1]).name else 0
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'run'
            argv = ['replay_compare.py', '--scope', 'live', '--baseline', str(Path(directory)/'old'),
                '--candidate', str(Path(directory)/'new'), '--at', '2026-09-20T03:00:00+00:00', '--output', str(output)]
            with patch.object(sys, 'argv', argv), patch.object(replay.subprocess, 'Popen', Child), patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(replay.main(), 1)
            self.assertEqual(json.loads((output/'comparison.json').read_text())['exit_codes'], {'baseline': 2, 'candidate': 0})
            for child in launched:
                self.assertEqual(child.command[child.command.index('--at')+1], '2026-09-20T03:00:00+00:00')
                self.assertNotIn('--evidence', child.command)


class MainResourceLifecycleTests(unittest.TestCase):
    """Real main processes, held at deterministic cleanup/output boundaries."""
    CHILD = r'''
import sys,json,builtins
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
from test_relevance_rules import load_module
m=load_module();phase=sys.argv[2];cache=Path(sys.argv[3]);output=sys.argv[4]
def ready():
    print('READY',flush=True)
    if sys.stdin.readline().strip()!='go':raise RuntimeError('missing release signal')
def wrap(original,name):
    def call(*a,**k):
        if phase==name or phase==name+'-fail':
            ready()
            if phase.endswith('-fail'):raise OSError('injected '+name+' failure')
        return original(*a,**k)
    return call
def collect(*a,**k):
    assert not (cache/'stale.json').exists(),'old response survived until network boundary'
    if phase in ('network','network-fail'):
        ready()
        if phase.endswith('-fail'):raise RuntimeError('injected network failure')
    return []
original_print=builtins.print
def guarded_print(*a,**k):
    if phase=='stdout' and a and str(a[0]).startswith('{'):
        original_print('READY',flush=True)
        if sys.stdin.readline().strip()!='go':raise RuntimeError('missing release signal')
    return original_print(*a,**k)
args=['--timezone','Asia/Singapore','--cache-dir',str(cache),'--format','json']
if output!='-':args+=['--output',output]
with patch.object(m,'collect_candidates_from_sources',side_effect=collect),patch.object(m,'prepare_cache_dir',side_effect=wrap(m.prepare_cache_dir,'cleanup')),patch.object(m,'write_output_file',side_effect=wrap(m.write_output_file,'json')),patch.object(m,'write_brief_scaffold_file',side_effect=wrap(m.write_brief_scaffold_file,'scaffold')),patch('builtins.print',side_effect=guarded_print):
    code=m.main(args)
raise SystemExit(code)
'''

    @classmethod
    def setUpClass(cls):
        cls.module = replay.load_code(Path(__file__).resolve().parents[1])

    def start(self, phase, cache, output):
        import subprocess
        return subprocess.Popen([sys.executable, '-c', self.CHILD, str(Path(__file__).parent), phase,
                                 str(cache), str(output) if output else '-'],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

    def wait_ready(self, child):
        import select
        self.assertTrue(select.select([child.stdout], [], [], 10)[0], 'child did not reach boundary')
        line = child.stdout.readline()
        self.assertEqual(line.strip(), 'READY')

    def finish(self, child):
        if child.poll() is None:
            return child.communicate('go\n', timeout=15)
        return child.communicate(timeout=15)

    def test_main_rejects_overlapping_real_resources_through_cleanup_and_output(self):
        for scenario, phase in [('same-cache', 'cleanup'), ('same-output', 'json'),
                                ('scaffold-alias', 'scaffold'), ('parent-alias', 'network'),
                                ('nested-cache', 'network'), ('output-in-cache', 'network'),
                                ('temporary-output', 'json'), ('stdout-cache', 'stdout')]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); first_cache=root/'cache';first_cache.mkdir()
                (first_cache/self.module.CACHE_MARKER_FILENAME).write_text('managed')
                (first_cache/'stale.json').write_text('old')
                first_output=root/'one.json';second_cache=root/'other-cache';second_output=root/'two.json'
                if scenario in {'same-cache','stdout-cache'}:second_cache=first_cache
                if scenario=='stdout-cache':first_output=None;second_output=None
                if scenario=='same-output':second_output=first_output
                if scenario=='scaffold-alias':second_output=first_output.with_suffix('.brief.md')
                if scenario=='parent-alias':
                    (root/'alias').symlink_to(root,target_is_directory=True);second_cache=root/'alias'/'cache'
                if scenario=='nested-cache':second_cache=first_cache/'child'
                if scenario=='output-in-cache':second_output=first_cache/'out.json'
                if scenario=='temporary-output':second_output=root/'.one.json.tmp'
                child=self.start(phase,first_cache,first_output)
                try:
                    self.wait_ready(child)
                    contender=self.start('none',second_cache,second_output)
                    stdout,stderr=contender.communicate(timeout=15)
                    self.assertEqual(contender.returncode,2,(stdout,stderr))
                    self.assertIn('in use',stderr)
                    if phase=='cleanup':self.assertEqual((first_cache/'stale.json').read_text(),'old')
                finally:
                    stdout,stderr=self.finish(child)
                self.assertEqual(child.returncode,0,(stdout,stderr))
                self.assertFalse((first_cache/'stale.json').exists())
                if first_output:
                    self.assertTrue(first_output.exists())
                    self.assertTrue(first_output.with_suffix('.brief.md').exists())

    def test_main_sibling_resources_run_concurrently_and_failure_releases_locks(self):
        for phase in ['network','cleanup-fail','network-fail','json-fail','scaffold-fail']:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);cache=root/'cache';output=root/'latest.json'
                child=self.start(phase,cache,output)
                try:
                    self.wait_ready(child)
                    sibling=self.start('none',root/'sibling-cache',root/'sibling.json')
                    out,err=sibling.communicate(timeout=15)
                    self.assertEqual(sibling.returncode,0,(out,err))
                finally:
                    out,err=self.finish(child)
                self.assertEqual(child.returncode,2 if phase.endswith('-fail') else 0,(out,err))
                if phase.endswith('-fail'):self.assertNotIn('"ok": true',out)
                restarted=self.start('none',cache,output)
                out,err=restarted.communicate(timeout=15)
                self.assertEqual(restarted.returncode,0,(out,err))
                self.assertTrue(output.exists())
                self.assertTrue(output.with_suffix('.brief.md').exists())


    def test_terminated_main_releases_resources_and_rejected_cache_stays_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache, output = root / 'cache', root / 'latest.json'
            child = self.start('network', cache, output)
            try:
                self.wait_ready(child)
                child.terminate()
                child.communicate(timeout=15)
                self.assertLess(child.returncode, 0)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=15)
            restarted = self.start('none', cache, output)
            out, err = restarted.communicate(timeout=15)
            self.assertEqual(restarted.returncode, 0, (out, err))
            for kind in ('unmarked', 'symlink', 'file'):
                with self.subTest(kind=kind):
                    target = root / ('rejected-' + kind)
                    if kind == 'file':
                        target.write_text('keep')
                        preserved = target
                    else:
                        actual = root / ('actual-' + kind)
                        actual.mkdir()
                        preserved = actual / 'stale.json'
                        preserved.write_text('keep')
                        if kind == 'symlink':
                            (actual / self.module.CACHE_MARKER_FILENAME).write_text('managed')
                            target.symlink_to(actual, target_is_directory=True)
                        else:
                            target = actual
                    rejected_output = root / ('rejected-' + kind + '.json')
                    rejected = self.start('none', target, rejected_output)
                    out, err = rejected.communicate(timeout=15)
                    self.assertEqual(rejected.returncode, 2, (out, err))
                    self.assertNotIn('old response survived', err)
                    self.assertNotIn('"ok": true', out)
                    self.assertEqual(preserved.read_text(), 'keep')
                    self.assertFalse(rejected_output.exists())
                    self.assertFalse(rejected_output.with_suffix('.brief.md').exists())


class ArticlePreparationSidecarTests(unittest.TestCase):
    def test_sidecar_requires_recorded_snapshot_and_exact_input(self):
        import copy
        from dataclasses import asdict, replace
        from test_relevance_rules import article_for
        m=replay.load_code(Path(__file__).resolve().parents[1])
        a=article_for(m,'Apple releases iOS 29','Apple released iOS 29 today.')
        a.key_facts=['The update is available.','It fixes a security issue.']
        before=asdict(a)
        kind=m.detect_event_kind(a.title,a.summary,a.key_facts)
        a._source_kind_snapshot=(a.title,a.summary,tuple(a.key_facts),kind)
        manual=replace(a,event_kind=kind)
        rows=replay.article_preparation_metadata([a,manual])
        self.assertIsNone(rows[1])
        self.assertEqual(asdict(a),before)
        restored=replace(a)
        self.assertEqual(replay.restore_article_preparation_metadata([restored,manual],json.loads(json.dumps(rows))),1)
        self.assertEqual(restored._source_kind_snapshot,a._source_kind_snapshot)
        self.assertEqual(asdict(restored),before)
        self.assertEqual(copy.deepcopy(restored)._source_kind_snapshot,a._source_kind_snapshot)
        for change in ('title','summary','facts','order','url','source'):
            other=replace(a)
            if change=='facts':other.key_facts=[*a.key_facts,'Changed fact.']
            elif change=='order':other.key_facts=list(reversed(a.key_facts))
            else:setattr(other,change,getattr(other,change)+' changed')
            with self.subTest(change=change):
                self.assertEqual(replay.restore_article_preparation_metadata([other],[rows[0]]),0)
                self.assertIsNone(other._source_kind_snapshot)
        self.assertEqual(replay.restore_article_preparation_metadata([restored],None),0)
        self.assertIsNone(restored._source_kind_snapshot)
        self.assertEqual(replay.restore_article_preparation_metadata([restored],[{'snapshot':['x']}]),0)
        with self.assertRaises(ValueError):replay.restore_article_preparation_metadata([restored],[])


    def test_worker_saves_actual_preparation_outside_behavior_trace(self):
        from types import SimpleNamespace
        from datetime import datetime
        from dataclasses import replace
        root=Path(__file__).resolve().parents[1]
        m=replay.load_code(root)
        fixture=json.loads((root/'tests/fixtures/p3_public_source_relations.json').read_text())
        row=next(r for r in fixture['natural_source_claims']['sources'] if r['id']=='s7')
        c=m.Candidate(row['source'],row['url'],row['title'],row['summary'])
        ev=m.capture_article_title_evidence(c.source,c.url,c.title,c.summary,tuple(row['key_facts']))
        at='2030-09-21T00:00:00+00:00';fixed=datetime.fromisoformat(at)
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'worker'
            args=SimpleNamespace(scope='live',evidence=None,output=output,baseline=root,at=at,postprocess_repeat=3)
            with patch.object(replay,'load_code',return_value=m), \
                 patch.object(m,'build_sources',return_value=[m.Source(c.source,'UTC')]), \
                 patch.object(m,'collect_candidates_from_sources',return_value=[c]), \
                 patch.object(m,'select_detail_candidates',return_value=[c]), \
                 patch.object(m,'fetch_detail_page_texts',return_value=['<article></article>']), \
                 patch.object(m,'capture_article_evidence',return_value=ev), \
                 patch.object(m,'extract_article',return_value=(c.title,c.summary,row['key_facts'],fixed,at,'synthetic','detail')), \
                 patch.object(m,'cluster_articles',wraps=m.cluster_articles) as cluster, \
                 patch('urllib.request.urlopen',side_effect=AssertionError('no network')), \
                 patch('sys.stdout',new_callable=io.StringIO):
                self.assertEqual(replay.worker(args),0)
            sidecar=json.loads((output/'article-preparation.json').read_text())
            behavior=json.loads((output/'behavior.json').read_text())
            self.assertEqual(len(sidecar),1)
            self.assertIsNotNone(sidecar[0])
            self.assertNotIn('_source_kind_snapshot',behavior['articles'][0])
            article=replace(cluster.call_args_list[0].args[0][0])
            self.assertIsNone(article._source_kind_snapshot)
            self.assertEqual(replay.restore_article_preparation_metadata([article],sidecar),1)
            self.assertEqual(tuple(sidecar[0]['snapshot'][2]),article._source_kind_snapshot[2])
            timing=json.loads((output/'timing.json').read_text())
            self.assertEqual([r['recorded_kind_snapshots'] for r in timing['postprocess']],[1,1,1])


if __name__ == '__main__':
    unittest.main()
