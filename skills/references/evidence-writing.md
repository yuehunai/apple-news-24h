# Evidence and writing

Read this file once before drafting. Eligibility and grouping are decided before factual coverage; a review obligation never requires publishing an incidental statement.

## Structured input

| Field | Meaning and use |
| --- | --- |
| `events` | Already decided starting groups. Preserve IDs, tiers, categories and source ownership unless original evidence demonstrates a policy conflict. |
| `claims` | Source-bound subject, action, object, qualifiers and spans. Binding is not permission to publish a separate story. Missing claims are not proof of weakness or duplication. |
| `summary`, `key_facts`, `must_include_facts`, `fact_sources` | Read together; the summary may contain unique facts. `origins` identifies sources/spans. `owned` means span ownership, not Apple ownership or eligibility. |
| `source_evidence` | Ordered original units for context, attribution and omissions. Use `unit_id`, not the ordinal as an array index. |
| `final_brief_queue`, `required_final_brief_titles` | Coverage obligations. A required title or fragment is not a publication instruction. |
| `deferred_events` | Review candidates. Their factual passages can support retained reports. Creating a new report requires the [eligibility test](eligibility.md#report-subject). |
| `brief_output`, `final_brief_markdown`, `*.brief.md` | Coverage scaffolds, not final copy. |

## Review queue

Give every material required fragment one disposition: a clause in an existing eligible report; a new report that passes the theme and action tests; or a specific exclusion reason. An unassigned fragment does not imply a new story. Do not repeatedly reopen settled decisions.

Read the referenced unit and its original neighbors when a pronoun, attribution, scope or report boundary is unclear. Adjacent `unprocessed_evidence` entries need not be adjacent prose. A `capture_status: discovery-only` item contains an excerpt, not verified full text: open the source if missing information could affect the report. Use recovered text only for the affected decisions. If unavailable, keep supported facts and record the remaining gap; do not invent text or promote the item.

## Fact record

After settling a report's eligibility and boundaries, use the [clause recorder](brief-records.md). For each source, first save its relevant propositions as complete Chinese publication-ready clauses, without comparing them with earlier sources. Then compare the saved entries and merge only complete equivalents. Deciding that a passage is already covered belongs to this second step; it cannot replace saving that source's own clauses. Keep the recorder's evolving list as the authoritative wording. Cross-source reading needed for eligibility or boundaries is unrestricted; reuse shared sources already read.

Save references and reasons for material omissions beside this run's output. Do not assign a source's entire retained-unit list to every paragraph citing it. If a unit has several material propositions, account for each; an ID, URL or generic “reviewed” reason does not account for its remaining content. No separate validation script is required.

## Establish the propositions

Write each clause with its **actual subject, operation, affected object, speaker or observer, scope, stage and conditions**. Keep negation, exceptions, numbers and modifiers attached to their own proposition; adjacency does not broaden their scope. Resolve ambiguous shorthand with explicit scope statements in the same source, without adding restrictions. A feature name alone does not describe its operation; the publisher need not be the observer. Resolve pronouns, omitted subjects and relative dates against the original ordered `source_evidence` units, including the original report date of quoted statements. `unprocessed_evidence` skips units already assigned elsewhere, so neighboring items in that list need not be adjacent prose. Follow their source positions before carrying an attribution across them. Expand collective references into the affected members and operations in the record.

Within an independently eligible report, assess material propositions by their factual role, not whether each qualifies as standalone news. An offer, prior result or operating condition may support the report; preserve its source, status and scope rather than excluding it under a report-level rule or recasting it as another kind of observation:

- **Retain** direct reports, observations, attributed plans, forecasts, responses and explanations relevant to this action. First-person observations of operation, failure or conditional behavior remain evidence when they accompany a preference or recommendation; separate the observation from that judgment. A reported speaker's technical explanation need not be a measured test; preserve the speaker without calling it measured or independently verified. “Possible”, “reportedly” or “rumor” describes certainty, not whether the statement is a reported claim or the writer's deduction. Neither repetition nor a second source is required.
- **Exclude first** the secondary writer's estimates or conclusions derived from reported facts or specifications, including added calculations, motives, significance, consequences and advice about what readers should infer. Attribution, calling it a forecast or placing it in a headline does not exempt the writer's deduction. Exclude the whole inferred proposition, not merely its inferential wording. Retain a neighboring baseline or observation only when the source reports it independently.
- **Reconcile after appending each source's clauses.** Compare the two saved clauses by actor, object, operation, scope, stage, dates, values, directions, conditions and degree, including qualitative quantifiers, negation and uncertainty. When the complete propositions are equivalent, keep one clause's complete wording, combine their references and remove the duplicate entry. Otherwise retain both attributed clauses as written. Do not replace them with a separate merged summary.
- **Check material relevance.** Supporting facts must describe or qualify the retained action's own object and operation. Sharing its device or source is insufficient: do not move an unrelated parameter into the action merely to account for it. Numbers, attribution and required flags do not make unrelated background mandatory. Record a concrete source, ownership or relevance reason for each omitted material fragment; do not reject a mixed paragraph under one “commentary” label.

## Write and check

Assemble the retained clauses verbatim into the paragraph and derive links from their references. Make any necessary wording change in that same clause list and check it against its passages before assembly. Do not reintroduce unselected material from cited units. When a later source contributes to the action, update the record and paragraph together before adding its URL. If drafting drops a source's only supported clause, remove that link too. When an added citation, including an incidental fragment from a weak source, supports the same named test or observation, record the passage or explicit reference establishing that shared observation identity, object, operation, scope and conditions. An unidentified observation cannot borrow that identity from matching symptoms or results in another source.

Preserve complete relevant lists and numeric series, attributes, units, per-model/region conditions, dates, prices, eligibility, official responses and operational limits. A name or umbrella label does not cover distinct outputs or input methods. State baseline attributes that define a configuration or comparison; “unchanged” alone is insufficient. Keep severity, thresholds and degree with the capability they qualify. Distinguish reaching a multiple of a baseline from increasing by that multiple.

Omit click paths and API syntax; retain settings, setup states and other prerequisites that determine whether or where a capability works, even in developer instructions. Historical release appendices are not current support matrices, but a relevant prior build or baseline may qualify the current change. Keep every value and condition with its specific operation, model, version and source. Name operations separately when they have different figures or conditions. Name the device containing a component rather than using an ambiguous pronoun.

Compare each relevant source unit with the actual Chinese clauses and omission reasons, then each clause with its supporting passage. A selected unit ID or a matching URL proves neither factual completeness nor agreement between sources. Check actors, operations, conditions and differing observations as well as numbers; do not infer causes or silently resolve contradictions. There is no target sentence count; use the length the material facts require.

After the factual checks, mark the action and its queue fragments complete, save the records and checked paragraphs beside this run's output, and continue with the remaining items. Assemble checked paragraphs without compressing their factual content.

Before returning:

1. Check the actual event-ID-to-bullet map against the [recorded boundary decisions](grouping.md#default-boundaries). Review every many-to-one or one-to-many mapping; a “retained” label, complete ID count or separate attribution does not validate a merge or split. Resolve unsupported boundary changes before delivery. Every current event ID needs a bullet, a demonstrated same-action duplicate or a specific exclusion. Close each required queue entry only after matching every material fragment to an actual clause or a specific omission reason. An action, source or unit ID shared with a clause does not by itself account for the entry’s remaining fragments.
2. Check each bullet's links against its resolved record, not a copied parent-event source list. Every URL must support an identified clause. Retain all such URLs, including repeated publishers, duplicate coverage and one source supporting multiple actions; a source need support only part of the bullet. Record unrelated fragments, canonical duplicates and excluded actions in the notes.


## Final prose pass

Apply this pass to the assembled copy after the last factual or boundary change; keep records and supporting links aligned with any edits.

Write the action and facts directly. Selection, exclusion, splitting, merging and category explanations belong in notes; do not include an excluded claim merely to label it speculation. Attribution and uncertainty belong beside a retained claim, not in a repeated ending such as “这些仍属传闻” or “这是该媒体的判断”. Retain distinct sourced facts such as a feature not yet enabled, an unresolved compatibility limit or an image identified as a simulation.

Express each proposition once. Inspect the last sentence **and trailing clauses**, then the rest of the paragraph, for repeated reporting status or credibility commentary. For example, “据 X 估计，可能达到 Y” already states the status; omit “这是预测，并非已实现结果”, wherever it appears. Keep a source's specific denial, confirmation status, missing field or operational limit when it adds a distinct fact. State each source’s period, population and measurement directly. Keep the reasoning used to reconcile scopes in the working notes; do not append what a figure cannot represent, replace or prove unless that statement is itself a distinct source fact. Remove generic significance, motives and consequences; moving them earlier does not fix them.

## Final format

Return the checked paragraphs verbatim under only `**软件与系统**` then `**硬件与产品**`, with one eligible report per bullet. Put every supporting link at that bullet's end: `（来源：[MacRumors](...), [9to5Mac](...)）`. Preserve multiple contributing URLs from the same publisher. A URL can support several independently eligible reports through different passages; it cannot establish their eligibility by itself.

For a truly empty category write `在指定时间窗口内，该分类下没有发现符合条件的新闻。` Do not add a status report, review explanation, cache note, file-only handoff or closing summary.
