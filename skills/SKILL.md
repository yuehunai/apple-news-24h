---
name: apple-news-24h
description: Use this skill only when explicitly invoked as $apple-news-24h or by an automation that asks for the reusable Apple 24-hour news brief. Do not use it implicitly in ordinary Apple, technology, or news conversations.
---

# Apple 24-Hour News Brief

A bare `$apple-news-24h` requests the complete Chinese brief for the preceding 24 hours, including when another agent invokes it. Collect fresh evidence, resolve its review items and deliver the brief in your final response. Continue while a next step is available; estimated workload is not an execution limit. If an actual blocker prevents completion, preserve progress and identify the blocked step, evidence and what is needed to resume.

## 1. Collect

Resolve the script relative to this skill directory and choose an output for this invocation:

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json
```

Use the requested IANA timezone when specified. Every invocation starts a new collection; memory, cached pages and earlier outputs do not establish this run's freshness. Wait for actual completion, then read the saved JSON. Stdout is status; `*.brief.md` is a coverage scaffold.

For a completed zero-event or suspiciously sparse first result, rerun the same command with network approval. If still sparse, add `--include-diagnostics`. Check `collection_warnings` even when there are many events. For a coverage failure, timestamp dispute or unavailable crawler, read only the relevant section of [collection](references/collection.md). Healthy sources may legitimately yield little news.

## 2. Establish report boundaries

The crawler's `events` are the starting groups. Preserve their IDs, decisions and source ownership unless current source evidence shows a specific policy conflict. `claims` bind facts; `required` demands review; `merge_warnings` demands a boundary check. None commands publication, merging or splitting.

**A separate bullet needs an independently eligible reporting subject.** A background sentence, incidental related-news mention, or non-theme passage in commentary or a weak third-party article may only supplement another eligible report. Without one, record its exclusion. Current tense, attribution, numbers, a heading or a different action verb do not alone make it news. A genuinely focused short report needs no minimum sentence, word or source count.

Before creating a bullet from review material, excluding an event or changing its category, read [eligibility](references/eligibility.md). Before merging or splitting, read [grouping](references/grouping.md). These files own those decisions; do not search the implementation or read unrelated policy files.

One coherent report can contain several observations, products, conditions and attributed positions. Decomposing its facts for checking does not mean publishing a bullet for every fact. Record the source evidence for any changed boundary; publication order, another headline angle or an extra parameter is insufficient.

## 3. Resolve and write

Before drafting, read [evidence and writing](references/evidence-writing.md) once and use its bundled clause recorder. Scan the event and queue index, then finish one to three reports at a time: summaries, facts, relevant source units and deferred support → clause/reference records and omission reasons → checked Chinese paragraphs. Read shared sources once. Narrow reads by ID or field when output is truncated.

Complete every event ID and every required material fragment. Review can result in support, an independently eligible report or exclusion; it is not a requirement to publish all captured text. Reopen live pages only when captured evidence is insufficient. Preserve important facts, conditions, source differences and all supporting URLs under their own attribution.

## 4. Deliver

Check each paragraph against its records and source passages, including the last sentence and trailing clauses. Remove repeated reporting-status disclaimers, review reasoning and generic conclusions. A sourced limitation or denial that adds a distinct fact remains.

Assemble the checked paragraphs verbatim. Return only `**软件与系统**` then `**硬件与产品**`, with source links at the end of each bullet. For an empty category use `在指定时间窗口内，该分类下没有发现符合条件的新闻。` Deliver the full brief itself, not just a file link, completion report or instruction for another agent to finish it.
