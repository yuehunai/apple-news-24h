"""Independent nested feeds share discovery capacity and retain input order."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import unittest
from test_relevance_rules import load_module


class DiscoveryBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_nested_requests_use_one_shared_limit_and_preserve_failures(self):
        m = self.m
        lock, barrier = threading.Lock(), threading.Barrier(2, timeout=2)
        active = peak = 0
        calls = []

        def fetch(url):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                calls.append(url)
            barrier.wait()
            with lock:
                active -= 1
            return None if url.endswith('failed') else url

        def collect(source, *_args, **_kwargs):
            return m.collection.fetch_discovery_pages([source + '/ok', source + '/failed'], fetch)

        result = m.collection.collect_candidates_from_sources(
            ['a', 'b'], Path('/unused'), {}, collect=collect, max_workers=2)
        self.assertEqual(result, ['a/ok', None, 'b/ok', None])
        self.assertEqual(sorted(calls), ['a/failed', 'a/ok', 'b/failed', 'b/ok'])
        self.assertEqual(peak, 2)

    def test_direct_call_is_ordered_and_does_not_keep_a_previous_executor(self):
        self.assertEqual(self.m.collection.fetch_discovery_pages([3, 1, 2], lambda n: n * 2), [6, 2, 4])

    def test_identity_reuse_is_local_and_input_sensitive(self):
        from apple_news_core import event_identity as identity
        from unittest.mock import patch
        args = ('Apple releases iOS 31', 'Apple released iOS 31 today.')
        with patch.object(identity, '_build_event_identity', wraps=identity._build_event_identity) as work:
            with identity._identity_preparation_scope():
                first = identity.build_event_identity(*args)
                with identity._identity_preparation_scope(reuse_existing=True):
                    self.assertIs(identity.build_event_identity(*args), first)
                    identity.build_event_identity(args[0], args[1] + ' Changed input.')
            self.assertEqual(work.call_count, 2)
            identity.build_event_identity(*args)
            self.assertEqual(work.call_count, 3)
        self.assertIsNone(identity._identity_preparation.get())
