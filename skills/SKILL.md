---
name: apple-news-24h
description: Use this skill only when explicitly invoked as $apple-news-24h or by an automation that asks for the reusable Apple 24-hour news brief. Do not use it implicitly in ordinary Apple, technology, or news conversations.
---

# Apple 24-Hour News Brief

A bare `$apple-news-24h` requests a Chinese brief for the preceding 24 hours. The crawler already collects, groups and classifies the evidence. Consume those results and resolve their review items rather than repeating the whole pipeline manually.

Deliver the complete brief in the final response. Continue while a next step is available; estimated workload is not an execution limit. If an actual blocker prevents completion, identify the blocked step and supporting evidence, preserve progress, and state what is needed to resume.

The detailed [policy](references/news_policy.md) remains authoritative. Consult its relevant section for an unresolved boundary or collection failure; ordinary runs do not require reading its entire implementation-rule catalogue.

## 1. Collect once

Each invocation starts a new collection. Run the crawler for this invocation even if saved memory describes an earlier same-day or unfinished run. Memory and existing output files are context, not proof that this invocation has collected fresh evidence. A bare invocation requests the complete brief, including when another agent invokes it; no separate review assignment is needed.

Resolve the script relative to this skill directory and choose an output for this run:

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json
```

Use the requested IANA timezone when one is specified. Wait for actual process completion, then read the JSON file; stdout is a status record and `*.brief.md` is a coverage scaffold, not the finished brief. Do not interrupt merely because collection takes longer than expected.

A completed zero-event or suspiciously sparse first result requires the **same command** rerun with network approval. If that rerun remains sparse, add `--include-diagnostics` and inspect source/fetch failures and discovery/detail counts. Healthy sources may legitimately yield little news. For unavailable sources use the policy's [source list](references/news_policy.md#sources) and [discovery/fallback rules](references/news_policy.md#candidate-discovery); do not fill gaps with weak items or old news.

Check `collection_warnings` even when the total event count is healthy: it marks unresolved source-window coverage. Use the same source's discovery/fallback rules to check that gap, and record any remaining limitation in the notes without treating an empty listing response as proof of no news.

If the crawler is unavailable, follow the policy’s manual fallback and record source URLs, publication times, actions and material facts; do not fabricate crawler JSON.

The managed cache is cleared at startup and contains only diagnostic evidence. Never reuse an older JSON or cached page as this run's freshness evidence.

## 2. Use the structured result

| Input | What to do |
| --- | --- |
| `events` | These have passed the crawler’s policy decisions. Preserve their ID boundaries, tiers, categories and source ownership. Reopen a decision only for a specific policy conflict demonstrated by source evidence, or a `merge_warning` requiring review. A warning alone does not justify merging or exclusion. Before splitting a retained event, record the captured passage that establishes a different substantive action or stage; another attribution, a separate article's focus, extra parameters or publication order alone is insufficient. |
| `claims` | When present, these are the source-bound identities: `subject`, `action`, `object`, qualifiers and `evidence_spans`. Use them before display titles or summaries when resolving boundaries. Several claims can share the same sentence or URL while naming different affected objects. Missing claims leave a boundary to source review; they do not establish duplication or weak relevance. |
| `summary`, `key_facts`, `must_include_facts`, `fact_sources` | Read these together: material facts may appear only in `summary`. Preserve the named actor, attribution, quantities and conditions. `origins` identifies the supporting source or exact span. `owned` marks binding to a projected claim's span, not Apple ownership or eligibility; `false` is not an exclusion reason. |
| `final_brief_queue` | Account for every required entry. For `unprocessed_evidence`, decide whether each material fragment completes an existing action, supports a separate eligible report, or is excluded by policy. In mixed sources, distinguish a local factual report from adjacent commentary; the parent’s roundup or opinion tone does not exclude a concrete local report. For a retained fragment, also check surrounding units in the same source for material format, device and version prerequisites or limitations of the same capability; a section boundary alone does not make those conditions unrelated. |
| `source_evidence` | Follow `evidence_id` to read the relevant unit and surrounding context when a fragment, pronoun, attribution or boundary needs clarification. Reopen a live page only if the captured evidence is insufficient. A queue entry with `capture_status: discovery-only` contains an excerpt, not verified full text: check the source for material missing claims when relevant. Use recovered text to resolve that item’s affected boundaries and map each material fragment to its supported action; keep a separate bullet only for a distinct eligible action. If unavailable, use only supported captured facts and record the unresolved gap; the marker does not promote the item. |
| `deferred_events` | Decide fragments in two cases. **Supporting a retained action:** keep sourced facts that complete or qualify it, with their URL. Test ownership and material relevance, not independent news eligibility: the supporting fact need not be newly disclosed or establish another action. A weak parent article does not disqualify its factual passages. **Creating a separate bullet:** identify the captured passage and resolve the weak reason under the eligibility rules below. This requires a concrete release, change or disclosure, or a dedicated report of current first-party functionality, support or operating conditions. Existing capabilities used only for context or advice do not qualify separately. |

When a review fragment describes a different action, establish its independent eligibility before creating a bullet, then determine its category from its own actor and operation. Background that recalls an earlier disclosure or repeats an unchanged assessment may support a retained action; a separate bullet requires evidence of current reporting beyond that background. A name, number or future period alone is not that evidence. It inherits neither eligibility nor category from the parent event. Facts that complete an existing action stay with that action.

Do not repeat full-article review or settled event decisions. Apparent implausibility, lack of independent corroboration, single-source coverage, differing versions/figures and a shared topic do not justify overruling an event. Preserve attribution and uncertainty. Review warnings and unassigned material: a queue fragment's `required` flag requires a decision, not automatic publication.

`must_include_facts` requires each distinct material proposition and qualifier, not verbatim sentences. The single evidence-to-draft workflow in section 4 applies to summaries, facts and required review fragments alike.

## 3. Resolve only the boundaries that need a decision

Before changing an event's eligibility, grouping or category, read the policy's [review decisions](references/news_policy.md#review-decisions). Determine those three outcomes separately from the source's actor, concrete operation, object, stage and defining scope. Compare bound `claims` first; absent claims are not evidence of weakness or duplication. A different category alone does not justify splitting an established action.

For a merge or split, record the source passages establishing the shared or distinct action, including any defining channel, observer, method or dataset. A shared device, publication date or source is insufficient. For exclusions, distinguish an ineligible parent article from its material support for a retained action and from an independently eligible local disclosure. Keep the original facts and URLs assigned to the actions they support.

## 4. Complete each action before moving on

Scan the event and queue index, then finish one to three actions at a time. Read their summaries, structured facts and relevant review fragments, including deferred sources; complete their records, paragraphs and checks before reading the next batch. Read shared sources once and assign their passages to the supported actions. If output is truncated, narrow the read by event, evidence ID or field.

Keep one short working record per action: **complete Chinese factual clause ready for publication → its own supporting source and unit references**, plus unit references and reasons for material omissions. A unit may contain several propositions: account for each material one in a clause or a specific omission reason before marking the unit complete. Citing a unit for one clause does not cover its remaining content. Attach references to each clause; use multiple references for equivalent coverage. Copied passages, shorthand and generic “retain relevant facts” labels are not resolved records. No separate checklist or validation script is needed.

### Establish the propositions from the evidence

Write each clause with its **actual subject, operation, affected object, speaker or observer, scope, stage and conditions**. Preserve the scope of negation, exceptions and modifiers. Resolve ambiguous shorthand with explicit scope statements in the same source, without adding restrictions. A feature name alone does not describe its operation; the publisher need not be the observer. Resolve pronouns, omitted subjects and relative dates against the original ordered `source_evidence` units, including the original report date of quoted statements. `unprocessed_evidence` skips units already assigned elsewhere, so neighboring items in that list need not be adjacent prose. Follow their source positions before carrying an attribution across them. Expand collective references into the affected members and operations in the record.

Within a retained action, decide each proposition separately:

- **Retain** direct reports, observations, attributed plans, forecasts, responses and explanations relevant to this action. First-person observations of operation, failure or conditional behavior remain evidence when they accompany a preference or recommendation; separate the observation from that judgment. A reported speaker's technical explanation need not be a measured test; preserve the speaker without calling it measured or independently verified. “Possible”, “reportedly” or “rumor” describes certainty, not whether the statement is a reported claim or the writer's deduction. Neither repetition nor a second source is required.
- **Exclude first** the secondary writer's estimates or conclusions derived from reported facts or specifications, including added calculations, motives, significance, consequences and advice about what readers should infer. Attribution, calling it a forecast or placing it in a headline does not exempt the writer's deduction. Exclude the whole inferred proposition, not merely its inferential wording. Retain a neighboring baseline or observation only when the source reports it independently.
- **Reconcile additional sources before drafting.** Compare each source's clause with the record. Add new facts and keep differing dates, values, scope, degree, directions or conditions under their own attribution, including qualitative quantifiers. Overlapping statements are not interchangeable merely because both can be true. Preserve affirmative, negative and uncertain claims at their actual stage; do not select a weaker common wording or collapse differences into generic uncertainty.
- **Check material relevance.** Supporting facts need not be newly disclosed or establish another Apple action, but must describe or qualify the retained action's own object and operation. Sharing its device or source is insufficient: do not move an unrelated parameter into the action merely to account for it. Numbers, attribution and required flags do not make unrelated background mandatory. Record a concrete source, ownership or relevance reason for each omitted material fragment; do not reject a mixed paragraph under one “commentary” label.

### Draft and verify against those propositions

Assemble the resolved Chinese clauses into the paragraph and derive links from their references; do not reconstruct facts from shorthand or reintroduce unselected material from cited units. When a later source contributes to the action, update the record and paragraph together before adding its URL. If drafting drops a source's only supported clause, remove that link too. A true duplicate may share wording only when actor, object, operation, scope and conditions agree.

Preserve complete relevant lists and numeric series, attributes, units, per-model/region conditions, dates, prices, eligibility, official responses and operational limits. A name or umbrella label does not cover distinct outputs or input methods. State baseline attributes that define a configuration or comparison; “unchanged” alone is insufficient. Keep severity, thresholds and degree with the capability they qualify. Distinguish reaching a multiple of a baseline from increasing by that multiple.

Omit click paths and API syntax; retain settings, setup states and other prerequisites that determine whether or where a capability works, even in developer instructions. Historical release appendices are not current support matrices, but a relevant prior build or baseline may qualify the current change. Keep every value and condition with its specific operation, model, version and source. Name operations separately when they have different figures or conditions. Name the device containing a component rather than using an ambiguous pronoun.

Compare each relevant source unit with the actual Chinese clauses and omission reasons, then each clause with its supporting passage. A selected unit ID or a matching URL proves neither factual completeness nor agreement between sources. Check actors, operations, conditions and differing observations as well as numbers; do not infer causes or silently resolve contradictions. There is no target sentence count; use the length the material facts require.

### Remove commentary before closing the action

Write the action and facts directly. Selection, exclusion, splitting, merging and category explanations belong in notes; do not include an excluded claim merely to label it speculation. Attribution and uncertainty belong beside a retained claim, not in a repeated ending such as “这些仍属传闻” or “这是该媒体的判断”. Retain distinct sourced facts such as a feature not yet enabled, an unresolved compatibility limit or an image identified as a simulation.

Express each proposition once. Inspect the last sentence **and trailing clauses**, then the rest of the paragraph, for repeated reporting status or credibility commentary. For example, “据 X 估计，可能达到 Y” already states the status; omit “这是预测，并非已实现结果”, wherever it appears. Keep a source's specific denial, confirmation status, missing field or operational limit when it adds a distinct fact. State each source’s period, population and measurement directly. Keep the reasoning used to reconcile scopes in the working notes; do not append what a figure cannot represent, replace or prove unless that statement is itself a distinct source fact. Remove generic significance, motives and consequences; moving them earlier does not fix them.

After these checks, mark the action and its queue fragments complete, save the records and checked paragraphs beside this run's output, and continue with the remaining items. Assemble checked paragraphs without shortening them again.

Before returning:

1. Every current event ID needs a bullet, a demonstrated same-action duplicate or a specific exclusion. Close each required queue entry only after matching every material fragment to an actual clause or a specific omission reason. An action, source or unit ID shared with a clause does not by itself account for the entry’s remaining fragments.
2. Check each bullet's links against its resolved record, not a copied parent-event source list. Every URL must support an identified clause. Retain all such URLs, including repeated publishers, duplicate coverage and one source supporting multiple actions; a source need support only part of the bullet. Record unrelated fragments, canonical duplicates and excluded actions in the notes.

## 5. Return the brief itself

Your final message to the caller must contain the checked paragraphs verbatim, even when another agent invoked the skill. Do not hand off delivery through a completion report, file link or instruction to use a saved draft. Output only `**软件与系统**` followed by `**硬件与产品**`, with one eligible action per bullet by default. Use readable Chinese and put all source links at the end of each bullet: `（来源：[MacRumors](...), [9to5Mac](...)）`.

End each bullet after its checked news facts and source links. Do not add a wrap-up or review explanation during final assembly.

For a truly empty category write `在指定时间窗口内，该分类下没有发现符合条件的新闻。` Do not append status, diagnostics, review explanations or cache notes.
