"""One replay/live compare entry point; test instrumentation, never a production CLI.

Run --help for usage. Each code tree executes in a fresh process. Frozen input is
read-only; unknown URLs, exhausted per-URL attempt budgets and network calls fail
closed. Historical text replay does not validate decoding or network performance.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import ExitStack
import copy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import statistics
import signal
import sys
import threading
import time
from unittest.mock import patch


class ReplayViolation(BaseException):
    """Bypass production's broad Exception recovery: missing evidence is not HTTP failure."""


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(plain(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def save(path, value):
    path.write_text(json.dumps(plain(value), ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def article_preparation_metadata(articles):
    """Optional non-semantic preparation, aligned with precluster Article order."""
    return [None if getattr(article, '_source_kind_snapshot', None) is None else {
        'source': article.source, 'url': article.url,
        'snapshot': plain(article._source_kind_snapshot),
    } for article in articles]


def restore_article_preparation_metadata(articles, rows):
    """Hydration must validate recorded inputs; absence means recomputation."""
    for article in articles:
        article._source_kind_snapshot = None
    if rows is None:
        return 0
    if not isinstance(rows, list) or len(rows) != len(articles):
        raise ValueError('Preparation sidecar must align with Article order')
    restored = 0
    for article, row in zip(articles, rows):
        if not isinstance(row, dict) or row.get('source') != article.source or row.get('url') != article.url:
            continue
        value = row.get('snapshot')
        if (not isinstance(value, (list, tuple)) or len(value) != 4
                or not all(isinstance(value[i], str) for i in (0, 1, 3))
                or not isinstance(value[2], (list, tuple))
                or not all(isinstance(fact, str) for fact in value[2])):
            continue
        snapshot = value[0], value[1], tuple(value[2]), value[3]
        if snapshot[:3] != (article.title, article.summary, tuple(article.key_facts)):
            continue
        article._source_kind_snapshot = snapshot
        restored += 1
    return restored


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_code(root):
    scripts = root / 'skills/scripts'
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location('replayed_apple_news', scripts / 'apple_news_24h.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Responses:
    def __init__(self, evidence, module):
        self.module = module
        self.lock = threading.Lock()
        self.calls = []
        self.attempts = defaultdict(list)
        self.used = defaultdict(int)
        cache = {}
        for path in sorted((evidence / 'cache').glob('*.json')):
            payload = json.loads(path.read_text())
            cache[payload['url']] = payload
        self.cache = cache
        request_file = evidence / 'requests.json'
        self.complete = request_file.exists()
        if self.complete:
            for row in sorted(json.loads(request_file.read_text()), key=lambda x: x['sequence']):
                self.attempts[row['url']].append(row)
            for url, rows in self.attempts.items():
                successes = [row for row in rows if 'error' not in row]
                if len(successes) > 1:
                    raise ReplayViolation(f'Multiple successes need per-attempt decoded evidence: {url}')
        else:
            # Exactly one saved success per URL; no invented failures or repeated success.
            for url in cache:
                self.attempts[url].append({'url': url, 'status': cache[url]['status']})

    def fetch(self, url, cache_dir, diagnostics, timeout=None, retries=None):
        url = self.module.iri_to_uri(url)
        retries = self.module.FETCH_RETRIES if retries is None else retries
        consumed = []
        with self.lock:
            for _ in range(retries + 1):
                index = self.used[url]
                if index >= len(self.attempts[url]):
                    raise ReplayViolation(f'Unknown URL or exhausted attempt budget: {url} at {index}')
                row = self.attempts[url][index]
                self.used[url] += 1
                consumed.append(row.get('sequence', index))
                if 'error' not in row:
                    if url not in self.cache:
                        raise ReplayViolation(f'Success has no decoded text: {url}')
                    payload = dict(self.cache[url], fetched_at=self.module.utc_now().isoformat())
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    save(cache_dir / f'{self.module.cache_key(url)}.json', payload)
                    self.calls.append({'url': url, 'attempts': consumed, 'result': 'text'})
                    return payload['text']
            error = row['error']
            diagnostics.setdefault('failed_fetches', []).append({'url': url, 'error': error})
            self.calls.append({'url': url, 'attempts': consumed, 'result': 'failure', 'error': error})
            return None

    def report(self):
        return {'complete_request_history': self.complete,
                'limitation': 'Decoded text boundary; retries grouped from recorded attempts, not transport validation.' if self.complete else 'Failed request history and repeated calls missing; unknown requests abort, no failures synthesized.',
                'calls': sorted(self.calls, key=lambda x: (x['url'], x['attempts'])),
                'unused_attempts': {u: len(rows) - self.used[u] for u, rows in self.attempts.items() if len(rows) != self.used[u]}}


def checked_paths(evidence, output):
    output = output.resolve()
    evidence = evidence.resolve() if evidence is not None else None
    if evidence is not None and (evidence == output or evidence in output.parents or output in evidence.parents):
        raise ValueError('Evidence and run output must be disjoint directories')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Run output must be new or empty; old results cannot imply success')
    return evidence, output


def worker(args):
    evidence, output = checked_paths(args.evidence, args.output)
    output.mkdir(parents=True, exist_ok=True)
    module = load_code(args.baseline.resolve())
    fixed = datetime.fromisoformat(args.at)
    if fixed.tzinfo is None:
        raise ValueError('--at requires timezone')

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.astimezone(timezone.utc).replace(tzinfo=None)

    live = args.scope == 'live'
    responses = None if live else Responses(evidence, module)
    trace = {'discovered': [], 'selected': [], 'extraction': [], 'articles': [], 'event_partitions': []}
    ticks = [(time.perf_counter(), time.process_time())]
    post_input = []
    original_collect = module.collect_candidates_from_sources
    original_select = module.select_detail_candidates
    original_fetch_detail = module.fetch_detail_page_texts
    original_cluster = module.cluster_articles

    def collect(*a, **kw):
        if args.scope == 'saved-details':
            historical = json.loads((evidence / 'latest.json').read_text())
            entries = {}
            for event in historical['events'] + historical.get('deferred_events', []):
                for source in event['sources']:
                    if source['url'] in responses.cache:
                        entries.setdefault(source['url'], source)
            result = [module.Candidate(source=row['name'], url=url, title=row['title'],
                       discovered_from='frozen-emitted-source-index')
                      for url, row in sorted(entries.items())]
        else:
            result = original_collect(*a, **kw)
        trace['discovered'] = plain(result)
        return result

    def select(*a, **kw):
        result = original_select(*a, **kw)
        trace['selected'] = plain(result)
        return result

    def detail(*a, **kw):
        result = original_fetch_detail(*a, **kw)
        ticks.append((time.perf_counter(), time.process_time()))
        return result

    def extraction(original, status):
        def wrapped(*a, **kw):
            result = original(*a, **kw)
            trace['extraction'].append({'candidate': plain(a[0]), 'path': status,
                'title': result[0], 'summary': result[1], 'key_facts': result[2],
                'published_utc': plain(result[3]), 'published_raw': result[4],
                'published_source': result[5], 'confidence': result[6]})
            return result
        return wrapped

    def cluster(articles):
        ticks.append((time.perf_counter(), time.process_time()))
        trace['articles'] = plain(articles)
        save(output / 'article-preparation.json', article_preparation_metadata(articles))
        post_input.extend(copy.deepcopy(articles))
        result = original_cluster(articles)
        trace['event_partitions'] = plain(result)
        ticks.append((time.perf_counter(), time.process_time()))
        return result

    def no_network(*a, **kw):
        raise ReplayViolation('Network is forbidden during decoded-text replay')

    cli_arguments = ['--hours', '24', '--timezone', 'Asia/Singapore', '--format', 'json',
                             '--include-diagnostics', '--cache-dir', str(output / 'cache'),
                             '--output', str(output / 'latest.json')]
    cli = module.parse_args(cli_arguments)
    code_hashes = {str(p.relative_to(args.baseline)): digest(p) for p in sorted((args.baseline / 'skills/scripts').rglob('*.py'))}
    provenance_file = evidence.parent / 'baseline-code.json' if evidence else None
    provenance = json.loads(provenance_file.read_text()) if provenance_file and provenance_file.exists() else {}
    save(output / 'manifest.json', {'at': args.at, 'baseline_sha': provenance.get('sha'),
         'production_matches_baseline': all(provenance.get('files', {}).get(p) == value for p, value in code_hashes.items()) if provenance else None, 'entry_sha256': digest(Path(__file__)), 'parameters': vars(cli), 'code_sha256': code_hashes,
         'input_index_sha256': {p.name: digest(p) for p in ([evidence / 'sha256.json', evidence / 'manifest.json', evidence / 'requests.json'] if evidence else []) if p.exists()},
         'scope': args.scope,
         'scope_limitation': 'Saved emitted source URLs only; no discovery, omitted historical candidates or unrecorded failures. Historical event grouping is not reused.' if args.scope == 'saved-details' else ('Concurrent live discovery through real main and transport; independent run resources.' if live else 'Full discovery through decoded text boundary.'),
         'precision_note': 'Preserves original raw/source/confidence; does not invent finer timestamp precision.'})
    try:
        with ExitStack() as stack:
            for name, replacement in {'datetime': FixedDatetime,
                'collect_candidates_from_sources': collect, 'select_detail_candidates': select,
                'fetch_detail_page_texts': detail, 'cluster_articles': cluster,
                'extract_article': extraction(module.extract_article, 'detail'),
                'fallback_article_from_discovery': extraction(module.fallback_article_from_discovery, 'discovery_fallback')}.items():
                stack.enter_context(patch.object(module, name, replacement))
            if live:
                original_run = module.run
                captured = []
                def capture_run(parsed):
                    data = original_run(parsed)
                    captured.append(data)
                    return data
                stack.enter_context(patch.object(module, 'run', capture_run))
                code = module.main(cli_arguments)
                if code:
                    save(output / 'failure.json', {'kind': 'live_main_failure', 'exit_code': code})
                    return code
                data = captured[0]
            else:
                stack.enter_context(patch.object(module, 'fetch_url', responses.fetch))
                stack.enter_context(patch('urllib.request.urlopen', no_network))
                stack.enter_context(patch('socket.socket.connect', no_network))
                data = module.run(cli)
                module.write_output_file(cli.output, data, 'json')
                module.write_brief_scaffold_file(Path(cli.output), data)
            ticks.append((time.perf_counter(), time.process_time()))
            timings = {name: {'wall': ticks[i+1][0] - ticks[i][0], 'cpu': ticks[i+1][1] - ticks[i][1]}
                       for i, name in enumerate(['collection', 'article_processing', 'event_processing', 'output'])}
            repetitions = []
            for _ in range(args.postprocess_repeat):
                articles = copy.deepcopy(post_input)
                start = time.perf_counter(), time.process_time()
                events = original_cluster(articles)
                serialized = [module.event_to_dict(e, timezone.utc) for e in events]
                repetitions.append({'wall': time.perf_counter() - start[0], 'cpu': time.process_time() - start[1],
                    'sha256': hashlib.sha256(json.dumps(serialized, sort_keys=True).encode()).hexdigest(),
                    'recorded_kind_snapshots': sum(row is not None for row in article_preparation_metadata(post_input))})
            save(output / 'timing.json', {'stages': timings, 'postprocess': repetitions,
                 'postprocess_median': {name: statistics.median(row[name] for row in repetitions) for name in ('wall', 'cpu')} if repetitions else None,
                 'scope': ('Live main: collection includes discovery, transport and parsing; postprocess excludes transport and is cluster + event serialization only.' if live else 'Collection includes discovery parsing and replay I/O; postprocess is cluster + event serialization only. No network performance claim.')})
            # Only explicit filesystem output paths are non-semantic in this structure.
            for field in ('path', 'resolved_path'):
                data['diagnostics']['cache'][field] = '<RUN_CACHE>'
            if live and 'brief_output' in data:
                expected = str(module.brief_scaffold_path(Path(cli.output)))
                if data['brief_output'] != expected:
                    raise ValueError('Unexpected brief_output path in live main result')
                data['brief_output'] = '<RUN_BRIEF_OUTPUT>'
            trace['result'] = data
            save(output / 'behavior.json', trace)
    except ReplayViolation as exc:
        save(output / 'failure.json', {'error': str(exc), 'kind': 'missing_replay_evidence'})
        return 2
    finally:
        save(output / 'responses.json', responses.report() if responses else {'mode': 'live', 'limitation': 'Real transport; successful decoded responses remain in this run cache. Failed fetches are recorded by production diagnostics, not synthesized replay history.'})
        save(output / 'code-after.json', {str(p.relative_to(args.baseline)): digest(p) for p in sorted((args.baseline / 'skills/scripts').rglob('*.py'))})
        if not (output / 'behavior.json').exists():
            save(output / 'partial_trace.json', trace)
    return 0



def separate_evidence(behavior):
    """Remove only P1's explicitly named additive fields, validating their links."""
    legacy = copy.deepcopy(behavior)
    records = legacy['result'].pop('source_evidence', {})
    for key, record in records.items():
        expected = hashlib.sha256(f"{record['source']}\0{record['url']}".encode()).hexdigest()[:24]
        if key != expected or record['article_id'] != key:
            raise ValueError('Invalid source evidence identity')
        ids = set()
        for unit in record['units']:
            raw = f"{key}\0{unit['origin']}\0{unit['ordinal']}\0{unit['kind']}\0{unit['text']}"
            if unit['unit_id'] != hashlib.sha256(raw.encode()).hexdigest()[:24] or unit['unit_id'] in ids:
                raise ValueError('Invalid or duplicate evidence unit identity')
            ids.add(unit['unit_id'])
    article_rows = list(legacy['articles'])
    article_rows.extend(article for event in legacy['event_partitions'] for article in event['articles'])
    for article in article_rows:
        evidence = article.pop('evidence', None)
        if records and evidence is None:
            raise ValueError('Article lost its source evidence')
        if evidence is not None:
            if records.get(evidence['article_id']) != evidence or evidence['url'] != article['url'] or evidence['source'] != article['source']:
                raise ValueError('Article evidence does not match original source registry')
    references = 0
    for event in legacy['result']['events'] + legacy['result']['deferred_events']:
        for source in event['sources']:
            key = source.pop('evidence_id', None)
            if records and key is None:
                raise ValueError('Serialized source lost its evidence reference')
            if key is not None:
                record = records.get(key)
                if record is None or (record['source'], record['url']) != (source['name'], source['url']):
                    raise ValueError('Serialized source references a different article')
                references += 1
    return legacy, {'source_records': len(records), 'units': sum(len(r['units']) for r in records.values()),
                    'serialized_references': references, 'valid': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True, help='Independent code tree')
    parser.add_argument('--baseline-artifact', type=Path, help='Existing baseline worker output directory; requires its behavior SHA256')
    parser.add_argument('--baseline-behavior-sha256')
    parser.add_argument('--candidate', type=Path, help='Optional second code tree, run in independent subprocess')
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--at', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--postprocess-repeat', type=int, choices=[0, 3], default=0)
    parser.add_argument('--scope', choices=['full', 'saved-details', 'live'], default='full')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.scope == 'live':
        if args.evidence or args.baseline_artifact or args.baseline_behavior_sha256 or (not args.worker and not args.candidate):
            parser.error('Live comparison requires two code trees and forbids historical evidence/artifact reuse')
    elif args.evidence is None:
        parser.error('Offline replay requires --evidence')
    if args.worker:
        return worker(args)
    checked_paths(args.evidence, args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.baseline_artifact:
        if not args.candidate or digest(args.baseline_artifact / 'behavior.json') != args.baseline_behavior_sha256:
            raise ValueError('Existing baseline needs candidate and matching explicit behavior SHA256')
        prior = json.loads((args.baseline_artifact / 'manifest.json').read_text())
        if prior['at'] != args.at or prior.get('scope', 'full') != args.scope:
            raise ValueError('Baseline time or replay scope differs')
        for name, fingerprint in prior['input_index_sha256'].items():
            if digest(args.evidence / name) != fingerprint:
                raise ValueError('Baseline frozen input differs')
    codes = ([] if args.baseline_artifact else [('baseline', args.baseline)]) + ([('candidate', args.candidate)] if args.candidate else [])
    statuses = {}
    with ExitStack() as logs:
        if args.scope == 'live':
            previous_handler = signal.getsignal(signal.SIGTERM)
            def terminate_parent(signum, frame):
                raise SystemExit(128 + signum)
            signal.signal(signal.SIGTERM, terminate_parent)
            logs.callback(signal.signal, signal.SIGTERM, previous_handler)
        running = []
        completed = False
        try:
            for label, code in codes:
                command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--baseline', str(code.resolve()),
                           '--at', args.at, '--output', str((args.output / label).resolve()),
                           '--postprocess-repeat', str(args.postprocess_repeat), '--scope', args.scope]
                if args.evidence is not None:
                    command += ['--evidence', str(args.evidence.resolve())]
                log = logs.enter_context((args.output / f'{label}.log').open('w'))
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                    env=dict(os.environ, PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1'))
                running.append((label, process))
                if args.scope != 'live':
                    statuses[label] = process.wait()
            if args.scope == 'live':
                for label, process in running:
                    statuses[label] = process.wait()
            completed = True
        finally:
            for label, process in running:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if label not in statuses:
                    statuses[label] = process.returncode
            if not completed:
                save(args.output / 'comparison.json', {'exit_codes': statuses, 'interrupted': True})
    report = {'exit_codes': statuses}
    if args.candidate and not any(statuses.values()):
        baseline_dir = args.baseline_artifact or args.output / 'baseline'
        baseline = json.loads((baseline_dir / 'behavior.json').read_text())
        candidate = json.loads((args.output / 'candidate/behavior.json').read_text())
        baseline, baseline_evidence = separate_evidence(baseline)
        candidate, candidate_evidence = separate_evidence(candidate)
        report['evidence_checks'] = {'baseline': baseline_evidence, 'candidate': candidate_evidence}
        report['baseline_behavior_sha256'] = digest(baseline_dir / 'behavior.json')
        report['equal'] = baseline == candidate
        report['different_sections'] = [k for k in baseline.keys() | candidate.keys() if baseline.get(k) != candidate.get(k)]
    save(args.output / 'comparison.json', report)
    print(json.dumps(report))
    return 1 if any(statuses.values()) or report.get('equal') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
