import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_24h_time_cache_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TimeCacheAndNewsroomTests(unittest.TestCase):
    def test_default_cache_dir_uses_platform_tempdir(self):
        module = load_module()

        self.assertEqual(module.DEFAULT_CACHE_DIR, Path(tempfile.gettempdir()) / "apple-news-24h")

    def test_prepare_cache_dir_clears_marked_directory_only(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_root:
            cache_dir = Path(temp_root) / "cache"
            cache_dir.mkdir()
            (cache_dir / module.CACHE_MARKER_FILENAME).write_text("managed\n", encoding="utf-8")
            (cache_dir / "stale.json").write_text("{}", encoding="utf-8")
            nested = cache_dir / "nested"
            nested.mkdir()
            (nested / "old.txt").write_text("old", encoding="utf-8")

            diagnostics = {}
            module.prepare_cache_dir(cache_dir, diagnostics)

            self.assertTrue((cache_dir / module.CACHE_MARKER_FILENAME).exists())
            self.assertFalse((cache_dir / "stale.json").exists())
            self.assertFalse(nested.exists())
            self.assertEqual(diagnostics["cache"]["removed_entries"], 2)

    def test_prepare_cache_dir_rejects_unmarked_non_default_directory_with_content(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_root:
            cache_dir = Path(temp_root) / "cache"
            cache_dir.mkdir()
            (cache_dir / "unrelated.txt").write_text("keep", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                module.prepare_cache_dir(cache_dir, {})

    def test_parse_datetime_value_handles_explicit_timezones(self):
        module = load_module()

        pt_value = module.parse_datetime_value("May 28, 2026 at 3:43 pm PT", "America/Los_Angeles")
        et_value = module.parse_datetime_value("May 28, 2026 at 6:43 pm ET", "America/New_York")
        cn_value = module.parse_datetime_value("2026 年 5 月 29 日 06:43", "Asia/Shanghai")

        self.assertEqual(pt_value.astimezone(timezone.utc).isoformat(), "2026-05-28T22:43:00+00:00")
        self.assertEqual(et_value.astimezone(timezone.utc).isoformat(), "2026-05-28T22:43:00+00:00")
        self.assertEqual(cn_value.astimezone(timezone.utc).isoformat(), "2026-05-28T22:43:00+00:00")

    def test_parse_datetime_value_handles_slash_dates_from_chinese_sites(self):
        module = load_module()

        value = module.parse_datetime_value("2026/6/1 21:46:34", "Asia/Shanghai")

        self.assertEqual(value.astimezone(timezone.utc).isoformat(), "2026-06-01T13:46:34+00:00")

    def test_extract_time_candidates_finds_slash_dates_from_article_body(self):
        module = load_module()
        page = '<span id="pubtime_baidu">2026/6/1 21:46:34</span>'

        self.assertIn(("2026/6/1 21:46:34", "body date pattern"), module.extract_time_candidates(page))

    def test_apple_newsroom_ignores_modified_and_video_upload_dates(self):
        module = load_module()
        page = f"""
        <html><head>
        <meta property="article:modified_time" content="2026-05-29T01:00:00Z">
        <script type="application/ld+json">
        {json.dumps({
            "@context": "https://schema.org",
            "@type": "VideoObject",
            "name": "Older Apple video",
            "uploadDate": "2026-05-29T01:00:00Z",
        })}
        </script>
        </head><body></body></html>
        """

        self.assertEqual(module.extract_apple_newsroom_time_candidates(page), [])

    def test_apple_newsroom_accepts_article_date_published(self):
        module = load_module()
        page = f"""
        <html><head>
        <script type="application/ld+json">
        {json.dumps({
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "Apple update",
            "datePublished": "2026-05-28T17:00:00Z",
            "dateModified": "2026-05-29T01:00:00Z",
        })}
        </script>
        </head><body></body></html>
        """

        self.assertEqual(
            module.extract_apple_newsroom_time_candidates(page),
            [("2026-05-28T17:00:00Z", "apple newsroom datePublished", True)],
        )


if __name__ == "__main__":
    unittest.main()
