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

## 2. Use the crawler's decisions

The crawler has selected the time window, captured sources, bound claims, and supplied initial groups, relevance, categories and fact plans. Use these results; do not repeat discovery or reclassify every source from scratch. Reopen a decision only for a coverage warning, `merge_warnings`, a specific source conflict, or material unresolved evidence. Binding a claim does not establish a separate reporting subject.

Scan `events`, `deferred_events` and the single `final_brief_queue` index. `required_final_brief_titles` and `*.brief.md` are alternate views, not additional work queues. Preserve event IDs and source ownership. Review each deferred item and required fragment, using the existing decisions where applicable; `required` means review, not publication or splitting.

On the first need to create a bullet from review material, exclude an event or change its category, read [eligibility](references/eligibility.md); for merging or splitting, read [grouping](references/grouping.md). Reuse those rules, revisiting only a disputed section. A separate bullet needs an independently eligible reporting subject; facts within one coherent report stay within it. Do not search the implementation.

## 3. Resolve and write

Read [evidence and writing](references/evidence-writing.md) once, then use its clause recorder. Work report by report from the summary, planned facts with source references, and associated unprocessed spans; save checked Chinese clauses. Reuse shared sources and settled decisions. Expand only the original passages needed to check a fact, attribution or boundary, rather than printing every source's full unit list by default. Keep batches within the tool's output limit; after truncation, continue from the last visible ID instead of repeating the batch.

Account for every event ID and required material fragment with a retained clause, justified boundary change or specific exclusion. Keep the clause record and a compact disposition index; refer to source/unit IDs instead of copying original text into additional ledgers. Preserve important facts, conditions, source differences and every supporting URL. Reopen live pages only when captured evidence is insufficient.

## 4. Deliver

Check final boundaries, material facts and source links against the records. Apply the writing guide's final prose pass, including sentence endings; a sourced limitation or denial that adds a distinct fact remains.

Assemble the checked paragraphs verbatim. Return only `**软件与系统**` then `**硬件与产品**`, with source links at the end of each bullet. For an empty category use `在指定时间窗口内，该分类下没有发现符合条件的新闻。` Deliver the full brief itself and end after the last news bullet (or empty-category sentence). Keep workflow notes, verification statements and disclaimers out of the final response; do not replace the brief with a file link or completion report.
