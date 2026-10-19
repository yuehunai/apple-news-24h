"""HTTPS requests declare their supported protocol without relaxing TLS verification."""
import io
from pathlib import Path
import ssl
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from test_relevance_rules import load_module


class TransportTests(unittest.TestCase):
    def test_https_declares_http1_and_reuses_verified_context(self):
        module = load_module()
        collection = module.collection
        collection._https_context.cache_clear()
        self.addCleanup(collection._https_context.cache_clear)
        real_create = ssl.create_default_context
        real_alpn = ssl.SSLContext.set_alpn_protocols
        contexts = []
        protocols = []
        def create():
            context = real_create()
            contexts.append(context)
            return context
        def alpn(context, names):
            protocols.append(names)
            return real_alpn(context, names)
        def response(request, **kwargs):
            self.assertIs(kwargs.get('context'), contexts[0] if contexts else None)
            result = io.BytesIO(b'<html>article</html>')
            result.headers = {'content-type': 'text/html; charset=utf-8'}
            result.status = 200
            return result
        with TemporaryDirectory() as directory, \
                patch.object(ssl, 'create_default_context', side_effect=create), \
                patch.object(ssl.SSLContext, 'set_alpn_protocols', alpn), \
                patch('urllib.request.urlopen', side_effect=response):
            for path in ('news', 'articles/example'):
                self.assertIsNotNone(module.fetch_url('https://example.com/' + path, Path(directory), {}, retries=0))
        self.assertEqual(protocols, [['http/1.1']])
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(contexts[0].check_hostname)
