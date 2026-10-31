# Evidence and writing

Read this file once before drafting. Decide reporting subjects first. An excluded subject cannot create a bullet, but its material evidence may support an existing report.

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

Use the retained events and categories as the report map. Reopen only the affected decision when a warning, original evidence or substantive unresolved material shows a conflict. A deferred subject needs the [eligibility test](eligibility.md#report-subject) before it receives a report.

Read each source's prepared contributions and `unprocessed_evidence` together, and route its material propositions to the reports they actually support, even when its own subject is excluded. Source is the reading unit; report remains the eligibility and boundary unit. An unassigned fragment does not imply a new story.

A `capture_status: discovery-only` item contains an excerpt, not verified full text: open the source if missing information could affect the report. Use recovered text only for the affected decisions. If unavailable, keep supported facts and record the remaining gap; do not invent text or promote the item.

## Fact record

Use the [clause recorder](brief-records.md) as the authoritative Chinese wording. Save missing or differing material with `book.add` from the source currently being read; attach a fully equivalent proposition with `book.cite`. Do not first write a combined account from several sources and then attach references. Only excluded material receives an omission reason; differences retain their speaker and scope under the reconciliation rules below.

Keep a compact event/queue → report or exclusion index for navigation and changed-boundary evidence. A material fragment is complete only through an actual clause citation or a specific exclusion; a prose pointer such as “written in another report” does not attach its source. Refer to source/unit/span IDs in the fixed JSON and derive URL coverage from clause references. Repeated excluded material may share an applicable reason, but mixed passages need separate treatment of their material propositions. No extra ledger or validation script is required.

## Establish the propositions

Write each clause with its **actual subject, operation, affected object, speaker or observer, scope, stage and conditions**. Keep negation, exceptions, numbers and modifiers attached to their own proposition; adjacency does not broaden their scope. Resolve shorthand using explicit scope statements in the same source, without adding restrictions. A feature name alone does not describe its operation; the publisher need not be the observer. Resolve pronouns, omitted subjects and relative dates against the original ordered `source_evidence` units, including the original report date of quoted statements. Adjacent `unprocessed_evidence` entries may skip assigned units: follow source positions and read original neighbors before carrying attribution across them. Expand collective references into the affected members and operations.

For an **already eligible report**, assess supporting propositions separately, including those in weak or excluded articles. Trace each proposition to its original role: quoting another writer does not turn that writer's inference into an external statement or forecast. Apply the exclusion first, then retain reported material with its source, status and scope.

- **Exclude** the article writer's own general product appraisals, and estimates or conclusions the writer derives from reported facts or specifications, including added calculations, motives, significance, consequences and advice about what readers should infer. Exclude the whole judgment or inference, not merely its evaluative wording. Retain a neighboring baseline or observation only when the source reports it independently.
- **Retain** material direct reports, observations, and attributed statements, assessments, plans, forecasts, responses and explanations relevant to this action. First-person observations of operation, failure or conditional behavior remain evidence when they accompany a preference or recommendation; separate the observation from that judgment. A reported speaker's technical explanation need not be a measured test; preserve the speaker without calling it measured or independently verified. Qualitative wording or uncertainty does not turn a reported speaker’s assessment into the article writer’s inference. Attribution alone does not make generic praise or significance material; retain specific explanations, forecasts, conditions or observed behavior. Neither repetition nor a second source is required.
- **Reconcile complete propositions.** Compare actor, object, operation, scope, stage, dates, values, directions, conditions and degree, including qualitative quantifiers, negation and uncertainty. Equivalent propositions share wording and references; differences retain their own attribution. When compound clauses partly overlap, revise them within the same report so the shared proposition appears once and each distinct condition or fact remains with its sources. This is factual deduplication, not a new report boundary or permission to compress away differences.
- **Check material relevance.** Supporting facts must describe or qualify the retained action's own object and operation. Sharing its device or source is insufficient: do not move an unrelated parameter into the action merely to account for it. Numbers, attribution and required flags do not make unrelated background mandatory. Record a concrete source, ownership or relevance reason for each omitted material fragment; do not reject a mixed paragraph under one “commentary” label.

## Write and check

Assemble the retained clauses verbatim into the paragraph and derive links from their references. Make any necessary wording change in that same clause list and check it against its passages before assembly. Do not reintroduce unselected material from cited units. When a later source contributes to the action, update the record and paragraph together before adding its URL. If drafting drops a source's only supported clause, remove that link too. For a reported statement, match the speaker and complete proposition; a retelling need not repeat the interview venue. Keep venue details attributed only to a source that establishes them. For a named test or observation, require passages or explicit references establishing the shared observer, object, operation, scope and conditions; matching symptoms or results alone cannot establish that identity.

Preserve complete relevant lists and numeric series, attributes, units, per-model/region conditions, dates, prices, eligibility, official responses and operational limits. A name or umbrella label does not cover distinct outputs or input methods. State baseline attributes that define a configuration or comparison; “unchanged” alone is insufficient. Keep severity, thresholds and degree with the capability they qualify. Distinguish reaching a multiple of a baseline from increasing by that multiple.

Omit click paths and API syntax; retain settings, setup states and other prerequisites that determine whether or where a capability works, even in developer instructions. Historical release appendices are not current support matrices, but a relevant prior build or baseline may qualify the current change. Keep each value with its operation, model, version and source. Name operations separately when they have different figures or conditions. Name the device containing a component rather than using an ambiguous pronoun.

Compare each relevant source proposition with the Chinese clauses or omission reason, then each clause with its passage. Reuse completed checks; a later edit reopens only affected clauses/reports. Check actors, operations, conditions, differing observations and availability stage as well as numbers. Preserve whether each capability is available, planned or not yet enabled in the Chinese clause itself; a condition does not convey its stage. Do not infer causes or silently resolve contradictions. There is no target sentence count.

Before returning:

1. Check the actual event-ID-to-bullet map against the [recorded boundary decisions](grouping.md#default-boundaries). Review every many-to-one or one-to-many mapping; a “retained” label, complete ID count or separate attribution does not validate a merge or split. Resolve unsupported boundary changes before delivery. Every current event ID needs a bullet, a demonstrated same-action duplicate or a specific exclusion. Close each required queue entry only after matching every material fragment to an actual clause or a specific omission reason. An action, source or unit ID shared with a clause does not by itself account for the entry’s remaining fragments.
2. Reconcile every retained source’s material propositions with actual clause references or specific exclusions, including sources with no unprocessed spans; its URL appearing elsewhere does not complete this check. Every contributing source must attach to an actual clause, and every bullet URL must support one. Derive links from clause references, not a copied parent-event source list. Retain all supporting URLs, including repeated publishers, duplicate coverage and one source supporting multiple actions; a source need support only part of the bullet. Record unrelated fragments, canonical duplicates and excluded actions in the notes.

Mark reports and their queue fragments complete only after these checks. Assemble the checked clauses without another rewrite.

## Final prose pass

Apply this pass to the assembled copy after the last factual or boundary change; keep records and supporting links aligned with any edits.

Write the action and facts directly. Selection, exclusion, splitting, merging and category explanations belong in notes; do not include an excluded claim merely to label it speculation. Attribution and uncertainty belong beside a retained claim, not in a repeated ending such as “这些仍属传闻” or “这是该媒体的判断”. Retain distinct sourced facts such as a feature not yet enabled, an unresolved compatibility limit or an image identified as a simulation.

Express each proposition once. Inspect the last sentence **and trailing clauses**, then the rest of the paragraph, for repeated reporting status or credibility commentary. For example, “据 X 估计，可能达到 Y” already states the status; omit “这是预测，并非已实现结果”. Keep a source's specific denial, confirmation status, missing field or operational limit when it adds a distinct fact. State each source’s period, population and measurement directly. Keep scope-reconciliation reasoning in working notes; do not append what a figure cannot represent, replace or prove unless that statement is a distinct source fact. Remove generic praise, significance, motives and consequences, even when attributed; retain concrete reported explanations and forecasts.

## Final format

Use the entrypoint's two-section format, with one eligible report per bullet. Put its supporting links at the end: `（来源：[MacRumors](...), [9to5Mac](...)）`.
