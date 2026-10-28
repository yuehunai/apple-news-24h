# Evidence and writing

Read this file once before drafting. Eligibility and grouping are decided before factual coverage; a review obligation never requires publishing an incidental statement.

## Structured input

| Field | Meaning and use |
| --- | --- |
| `events` | Already decided starting groups. Preserve IDs, tiers, categories and source ownership unless original evidence demonstrates a policy conflict. |
| `claims` | Source-bound subject, action, object, qualifiers and spans. Binding is not permission to publish a separate story. Missing claims are not proof of weakness or duplication. |
| `summary`, `key_facts`, `must_include_facts`, `fact_sources` | Read together; the summary may contain unique facts. `origins` identifies sources/spans. `owned` means span ownership, not Apple ownership or eligibility. |
| `source_evidence` | Original units for checking the prepared facts and unresolved material. Use `unit_id`, not the ordinal as an array index; expand surrounding prose when needed. |
| `evidence_dispositions` | Existing assigned/excluded spans and reasons. Inherit these decisions unless contradicted by source evidence; assigned does not mean already expressed in Chinese. |
| `final_brief_queue` | The review index. Link already handled events/fragments to their existing decisions; a required fragment is not a publication instruction. |
| `deferred_events` | Review candidates. Their factual passages can support retained reports. Creating a new report requires the [eligibility test](eligibility.md#report-subject). |
| `required_final_brief_titles`, `brief_output`, `final_brief_markdown`, `*.brief.md` | Alternate coverage views. Do not read or register them as another queue. |

## Review queue

Start with each event's summary, planned facts and source references; these are prepared inputs, not a request to redo extraction, eligibility or clustering. Missing `claims` or an `owned: false` field alone does not invalidate an event's decisions. Reopen only the affected decision when a warning, original evidence or substantive unresolved material shows a conflict.

Process the associated `unprocessed_evidence` during the same source read. Give every material fragment a clause, an independently eligible report or a specific exclusion. A fragment already resolved elsewhere links to that decision; do not read, rewrite or decide it again. A reference to the same unit does not cover its other propositions. An unassigned fragment does not imply a new story.

Read the referenced unit and its original neighbors when a pronoun, attribution, scope or report boundary is unclear. Adjacent `unprocessed_evidence` entries need not be adjacent prose. A `capture_status: discovery-only` item contains an excerpt, not verified full text: open the source if missing information could affect the report. Use recovered text only for the affected decisions. If unavailable, keep supported facts and record the remaining gap; do not invent text or promote the item.

## Fact record

Use the [clause recorder](brief-records.md) as the authoritative Chinese wording. Check each source's relevant propositions against the existing clauses for that report. Save new or differing propositions; for a complete equivalent, directly attach the source/unit reference and an equivalence reason to the existing clause. Rewriting and saving a duplicate sentence first is unnecessary. A match must include conditions, degree, negation and attribution, not merely the topic.

Keep a compact disposition index beside the clauses: event/queue/fragment ID → report/clause or specific exclusion reason, with source/unit/span where needed. Store boundary evidence for changed groups. Refer to the fixed JSON instead of copying all original units into more ledgers; derive source/URL coverage from the clause references. An ineligible source or repeated non-factual material can share one applicable reason, but mixed material still needs specific treatment of its important propositions. An ID or generic “reviewed” label is not coverage. No extra validation script is required.

## Establish the propositions

Write each clause with its **actual subject, operation, affected object, speaker or observer, scope, stage and conditions**. Keep negation, exceptions, numbers and modifiers attached to their own proposition; adjacency does not broaden their scope. Resolve ambiguous shorthand with explicit scope statements in the same source, without adding restrictions. A feature name alone does not describe its operation; the publisher need not be the observer. Resolve pronouns, omitted subjects and relative dates against the original ordered `source_evidence` units, including the original report date of quoted statements. `unprocessed_evidence` skips units already assigned elsewhere, so neighboring items in that list need not be adjacent prose. Follow their source positions before carrying an attribution across them. Expand collective references into the affected members and operations in the record.

Within an independently eligible report, assess material propositions by their factual role, not whether each qualifies as standalone news. An offer, prior result or operating condition may support the report; preserve its source, status and scope rather than excluding it under a report-level rule or recasting it as another kind of observation:

- **Retain** direct reports, observations, attributed plans, forecasts, responses and explanations relevant to this action. First-person observations of operation, failure or conditional behavior remain evidence when they accompany a preference or recommendation; separate the observation from that judgment. A reported speaker's technical explanation need not be a measured test; preserve the speaker without calling it measured or independently verified. “Possible”, “reportedly” or “rumor” describes certainty, not whether the statement is a reported claim or the writer's deduction. Neither repetition nor a second source is required.
- **Exclude first** the article writer's estimates or conclusions derived from reported facts or specifications, including added calculations, motives, significance, consequences and advice about what readers should infer. Quoting or reprinting the writer's calculation or conditional extrapolation does not turn it into a reported proposal or forecast. Exclude the whole inferred proposition, not merely its inferential wording. Retain a neighboring baseline or observation only when the source reports it independently.
- **Reconcile complete propositions.** Compare actor, object, operation, scope, stage, dates, values, directions, conditions and degree, including qualitative quantifiers, negation and uncertainty. Equivalent propositions share wording and references; differences retain their own attribution. When compound clauses partly overlap, revise them within the same report so the shared proposition appears once and each distinct condition or fact remains with its sources. This is factual deduplication, not a new report boundary or permission to compress away differences.
- **Check material relevance.** Supporting facts must describe or qualify the retained action's own object and operation. Sharing its device or source is insufficient: do not move an unrelated parameter into the action merely to account for it. Numbers, attribution and required flags do not make unrelated background mandatory. Record a concrete source, ownership or relevance reason for each omitted material fragment; do not reject a mixed paragraph under one “commentary” label.

## Write and check

Assemble the retained clauses verbatim into the paragraph and derive links from their references. Make any necessary wording change in that same clause list and check it against its passages before assembly. Do not reintroduce unselected material from cited units. When a later source contributes to the action, update the record and paragraph together before adding its URL. If drafting drops a source's only supported clause, remove that link too. When an added citation, including an incidental fragment from a weak source, supports the same named test or observation, record the passage or explicit reference establishing that shared observation identity, object, operation, scope and conditions. An unidentified observation cannot borrow that identity from matching symptoms or results in another source.

Preserve complete relevant lists and numeric series, attributes, units, per-model/region conditions, dates, prices, eligibility, official responses and operational limits. A name or umbrella label does not cover distinct outputs or input methods. State baseline attributes that define a configuration or comparison; “unchanged” alone is insufficient. Keep severity, thresholds and degree with the capability they qualify. Distinguish reaching a multiple of a baseline from increasing by that multiple.

Omit click paths and API syntax; retain settings, setup states and other prerequisites that determine whether or where a capability works, even in developer instructions. Historical release appendices are not current support matrices, but a relevant prior build or baseline may qualify the current change. Keep every value and condition with its specific operation, model, version and source. Name operations separately when they have different figures or conditions. Name the device containing a component rather than using an ambiguous pronoun.

Compare each relevant source proposition with the Chinese clauses or omission reason, then each clause with its passage. Reuse completed checks; a later edit reopens only affected clauses/reports. A selected unit ID or matching URL proves neither completeness nor agreement. Check actors, operations, conditions, differing observations and availability stage as well as numbers. Preserve whether each capability is available, planned or not yet enabled in the Chinese clause itself; a condition does not convey its stage. Do not infer causes or silently resolve contradictions. There is no target sentence count.

Mark the report and associated queue fragments complete after those checks. Save the records and continue; final assembly uses the checked clauses without another rewrite.

Before returning:

1. Check the actual event-ID-to-bullet map against the [recorded boundary decisions](grouping.md#default-boundaries). Review every many-to-one or one-to-many mapping; a “retained” label, complete ID count or separate attribution does not validate a merge or split. Resolve unsupported boundary changes before delivery. Every current event ID needs a bullet, a demonstrated same-action duplicate or a specific exclusion. Close each required queue entry only after matching every material fragment to an actual clause or a specific omission reason. An action, source or unit ID shared with a clause does not by itself account for the entry’s remaining fragments.
2. Reconcile every retained event's `sources` with clause references or a specific exclusion, including sources with no unprocessed spans. Then check that every contributing source is attached to an actual clause and every bullet URL supports an identified clause. A note promising to add a source is unfinished. Derive links from clause references, not a copied parent-event source list. Retain all supporting URLs, including repeated publishers, duplicate coverage and one source supporting multiple actions; a source need support only part of the bullet. Record unrelated fragments, canonical duplicates and excluded actions in the notes.


## Final prose pass

Apply this pass to the assembled copy after the last factual or boundary change; keep records and supporting links aligned with any edits.

Write the action and facts directly. Selection, exclusion, splitting, merging and category explanations belong in notes; do not include an excluded claim merely to label it speculation. Attribution and uncertainty belong beside a retained claim, not in a repeated ending such as “这些仍属传闻” or “这是该媒体的判断”. Retain distinct sourced facts such as a feature not yet enabled, an unresolved compatibility limit or an image identified as a simulation.

Express each proposition once. Inspect the last sentence **and trailing clauses**, then the rest of the paragraph, for repeated reporting status or credibility commentary. For example, “据 X 估计，可能达到 Y” already states the status; omit “这是预测，并非已实现结果”, wherever it appears. Keep a source's specific denial, confirmation status, missing field or operational limit when it adds a distinct fact. State each source’s period, population and measurement directly. Keep the reasoning used to reconcile scopes in the working notes; do not append what a figure cannot represent, replace or prove unless that statement is itself a distinct source fact. Remove generic significance, motives and consequences; moving them earlier does not fix them.

## Final format

Use the entrypoint's two-section format, with one eligible report per bullet. Put links at the end: `（来源：[MacRumors](...), [9to5Mac](...)）`. Preserve all contributing URLs, including multiple URLs from one publisher. A URL may support several independently eligible reports through their own passages; it cannot establish their eligibility.
