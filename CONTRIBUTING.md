# Contributing

Contributions are welcome, especially fixes for source parsing, timestamp handling, event grouping, and relevance rules.

## Development Setup

Use Python 3.9 or later on macOS or Linux; resource locking requires POSIX `fcntl`. The runtime and test tools use only the standard library. See the [architecture overview](README.md#architecture) for module responsibilities.

Run tests:

```bash
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m unittest discover -s tests
```

Run a syntax check:

```bash
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m compileall -q skills/scripts
```

## Contribution Rules

- Keep the skill explicitly invoked only. Do not change `policy.allow_implicit_invocation: false`.
- Prefer generic rules over one-off title or URL hard-coding.
- Add or update an offline regression test for every relevance, timestamp, cache, or grouping rule change.
- Do not commit live cache files, raw article pages, generated `latest.json`, logs, or local environment files.
- Do not add third-party dependencies unless the benefit clearly outweighs the automation setup cost.
- Preserve source attribution in final summaries.
- Update `skills/references/news_policy.md` when source or decision rules change. Update `skills/SKILL.md` when the calling agent's workflow changes; keep repository maintenance instructions out of the skill entry point.

## Source And Rule Changes

When adding or changing a source:

- Add the feed/page URL and default timezone to `skills/references/news_policy.md`.
- Prefer feed discovery first, then homepage/channel/date archive fallback.
- Verify detail-page timestamp parsing.
- Add a test fixture or focused unit test for the behavior being protected.

When changing filtering or grouping:

- Include positive and negative tests.
- Avoid broad terms that turn tutorials, deals, podcasts, or opinion posts into news.
- Keep cross-language grouping tokens conservative enough to avoid unrelated event merges.
- Change the responsible module rather than adding another decision in output assembly. A shared product name, publisher or URL is not sufficient evidence of the same action.
- Preserve each claim's source and material qualifiers; check that unassigned fragments remain visible in `final_brief_queue`. A linked URL alone does not prove fact coverage.
- Keep existing regression protection. Explain any corrected expectation with source evidence; use minimal relevant fixtures instead of full cached pages.

For reproducible comparisons, use [tests/REPLAY.md](tests/REPLAY.md). Fixed-input replay, unit tests and live collection establish different properties; reuse valid results for unchanged code instead of repeating the whole suite for documentation edits.

## Live Smoke Testing

Live tests depend on third-party websites and should not be required for every pull request. When doing a live smoke test, run:

```bash
python3 skills/scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json --include-diagnostics
```

Review `latest.json` and its source evidence, not just event counts or titles. Treat `*.brief.md` as a coverage scaffold. Use separate cache and output paths for independent runs, and keep all generated files outside the commit.
