# Clause recorder

Use `scripts/brief_records.py` for the authoritative clause list and assembly. It checks references, preserves wording and derives links; it does not decide eligibility, boundaries, completeness or equivalence. Batch calls to this API as useful; do not build another fact store or rewriting layer.

Import it from this skill's `scripts` directory. Use a new record file beside the current output, then reopen that same file to continue. For a retained input `event`, inherit its category when creating the report:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(skill_directory / "scripts"))
from brief_records import BriefRecords

evidence = json.loads(Path("latest.json").read_text())["source_evidence"]
book = BriefRecords("clauses.json", evidence)
category = {"software_systems": "软件与系统", "hardware_products": "硬件与产品"}[event["category"]]
book.add_report("report-key", category, [event["id"]])
first = book.add("report-key", complete_chinese_clause, [(source_id, unit_id)])
```

Keep a change of speaker or observer in a separate clause. When splitting or combining clauses, verify relationships as well as values; do not add a speaker’s reason, basis or method just to connect independently reported facts. Each operation saves immediately. References use actual `source_evidence` keys and `unit_id` values, not array positions. A clause can reference several units. If missing text was recovered, save its passages beside this run using the same source/unit structure and include that evidence when opening the recorder; preserve the original crawler output.

Check each source against the saved clauses of the report it supports, which may belong to another event:

- `book.cite(clause_id, references, reason)` attaches a fully equivalent source proposition to an existing clause without rewriting it. Match the complete proposition and record why it is equivalent. If only part of a compound clause matches, first use `revise` and `add` to separate the shared proposition from the remaining original facts, then cite the shared clause; do not drop the source because it cannot support the whole compound clause.
- `book.merge(keep_id, remove_id, reason)` keeps the selected saved wording and combines references. Use it only after confirming complete equivalence; it accepts no replacement summary. Removed wording remains in the record.
- `book.revise(clause_id, text, reason)` updates wording after checking the passages; preserve each fact, condition and source when separating partly overlapping propositions. `book.omit(clause_id, reason)` records a substantive omission; duplicate propositions use `merge`. Do not replace the paragraph with a compressed summary.
- `book.move(clause_id, report_key)` applies a justified boundary or category correction by moving the unchanged clause to an existing report.
- `book.snapshot()` returns a copy for inspection. Reuse the current report's clause IDs; do not copy and scan the entire book before every addition. Keep event/queue decisions and omissions in a compact index, without another clause list or copied original text.

After the [factual and final prose checks](evidence-writing.md#write-and-check), call `book.check(report_key)`. Subsequent edits invalidate that report's check. Finish with `book.write("final_brief.md")` and return that text verbatim. Assembly fails while reports are unchecked or their saved references disagree with the supplied evidence; it does not validate the semantic decisions.
