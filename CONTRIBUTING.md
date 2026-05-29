# Contributing

Contributions are welcome, especially fixes for source parsing, timestamp handling, event grouping, and relevance rules.

## Development Setup

This project currently uses only the Python standard library.

Run tests:

```bash
python3 -m unittest discover -s tests
```

Run a syntax check:

```bash
python3 -m py_compile scripts/apple_news_24h.py
```

## Contribution Rules

- Keep the skill explicitly invoked only. Do not change `policy.allow_implicit_invocation: false`.
- Prefer generic rules over one-off title or URL hard-coding.
- Add or update an offline regression test for every relevance, timestamp, cache, or grouping rule change.
- Do not commit live cache files, raw article pages, generated `latest.json`, logs, or local environment files.
- Do not add third-party dependencies unless the benefit clearly outweighs the automation setup cost.
- Preserve source attribution in final summaries.

## Source And Rule Changes

When adding or changing a source:

- Add the feed/page URL and default timezone to `references/news_policy.md`.
- Prefer feed discovery first, then homepage/channel/date archive fallback.
- Verify detail-page timestamp parsing.
- Add a test fixture or focused unit test for the behavior being protected.

When changing filtering or grouping:

- Include positive and negative tests.
- Avoid broad terms that turn tutorials, deals, podcasts, or opinion posts into news.
- Keep cross-language grouping tokens conservative enough to avoid unrelated event merges.

## Live Smoke Testing

Live tests depend on third-party websites and should not be required for every pull request. When doing a live smoke test, run:

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json --include-diagnostics
```

Review `latest.json`, then delete it before committing.
