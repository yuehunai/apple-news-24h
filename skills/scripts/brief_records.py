"""Persist source-bound Chinese clauses and assemble the checked brief verbatim.

The caller decides eligibility, report boundaries and semantic equivalence.
This module never summarizes text or determines which propositions are equivalent.
"""

from copy import deepcopy
import json
from pathlib import Path


CATEGORIES = ("软件与系统", "硬件与产品")


class BriefRecords:
    def __init__(self, path, source_evidence):
        self.path = Path(path)
        self._sources = source_evidence
        self._units = {
            (source_id, unit["unit_id"]): unit
            for source_id, source in source_evidence.items()
            for unit in source["units"]
        }
        self._data = (json.loads(self.path.read_text(encoding="utf-8"))
                      if self.path.exists() else {"reports": {}, "clauses": {}})

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _required(value, name):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(name + " must be nonempty text")
        return value

    def _report(self, key):
        if key not in self._data["reports"]:
            raise ValueError("unknown report: " + str(key))
        return self._data["reports"][key]

    def _retained(self, key):
        clause = self._data["clauses"].get(key)
        if clause is None or clause["state"] != "retained":
            raise ValueError("clause must be an existing retained entry: " + str(key))
        return clause

    def _reference(self, source_id, unit_id):
        unit = self._units.get((source_id, unit_id))
        if unit is None:
            raise ValueError("unknown source unit: " + str((source_id, unit_id)))
        source = self._sources[source_id]
        return {"source_id": source_id, "unit_id": unit_id,
                "source": source["source"], "url": source["url"], "passage": unit["text"]}

    def add_report(self, key, category, event_ids=()):
        self._required(key, "report key")
        if category not in CATEGORIES or key in self._data["reports"]:
            raise ValueError("report needs a new key and a supported category")
        self._data["reports"][key] = {"category": category, "events": list(event_ids),
                                      "clauses": [], "checked": False}
        self._save()

    def add(self, report, text, references):
        """Save a complete clause before considering a merge; return its stable ID."""
        target = self._report(report)
        self._required(text, "clause")
        refs = [self._reference(*pair) for pair in dict.fromkeys(map(tuple, references))]
        if not refs:
            raise ValueError("a clause needs at least one supporting source unit")
        key = "c" + str(len(self._data["clauses"]) + 1)
        self._data["clauses"][key] = {"report": report, "text": text,
                                       "references": refs, "state": "retained"}
        target["clauses"].append(key)
        target["checked"] = False
        self._save()
        return key

    def merge(self, keep, remove, reason):
        """Record the caller's equivalence decision without accepting new wording."""
        first, second = self._retained(keep), self._retained(remove)
        self._required(reason, "equivalence reason")
        if keep == remove or first["report"] != second["report"]:
            raise ValueError("merge needs two saved clauses in the same report")
        existing = {(ref["source_id"], ref["unit_id"]) for ref in first["references"]}
        first["references"].extend(deepcopy(ref) for ref in second["references"]
                                   if (ref["source_id"], ref["unit_id"]) not in existing)
        second.update(state="merged", merged_into=keep, reason=reason)
        self._report(first["report"])["checked"] = False
        self._save()

    def revise(self, key, text, reason):
        """Correct one clause's wording; retain its earlier wording and references."""
        clause = self._retained(key)
        self._required(text, "clause")
        self._required(reason, "revision reason")
        clause.setdefault("revisions", []).append({"text": clause["text"], "reason": reason})
        clause["text"] = text
        self._report(clause["report"])["checked"] = False
        self._save()

    def omit(self, key, reason):
        clause = self._retained(key)
        self._required(reason, "omission reason")
        clause.update(state="omitted", reason=reason)
        self._report(clause["report"])["checked"] = False
        self._save()

    def move(self, key, report):
        """Apply a corrected report boundary without changing the saved clause."""
        clause = self._retained(key)
        target = self._report(report)
        previous = self._report(clause["report"])
        previous["clauses"].remove(key)
        target["clauses"].append(key)
        previous["checked"] = target["checked"] = False
        clause["report"] = report
        self._save()

    def snapshot(self):
        """Return a read-only-by-copy view for the caller's semantic review."""
        return deepcopy(self._data)

    def check(self, report):
        """Mark a report checked after the caller's source and prose review."""
        self._report(report)["checked"] = True
        self._save()

    def render(self):
        unchecked = [key for key, report in self._data["reports"].items()
                     if not report["checked"]]
        if unchecked:
            raise ValueError("reports still need review: " + ", ".join(unchecked))
        sections = []
        for category in CATEGORIES:
            bullets = []
            for report in self._data["reports"].values():
                if report["category"] != category:
                    continue
                clauses = [self._data["clauses"][key] for key in report["clauses"]
                           if self._data["clauses"][key]["state"] == "retained"]
                if not clauses:
                    continue
                links = {}
                for clause in clauses:
                    for ref in clause["references"]:
                        current = self._reference(ref["source_id"], ref["unit_id"])
                        if current != ref:
                            raise ValueError("saved reference differs from this run's source evidence")
                        links.setdefault(ref["url"], ref["source"])
                citations = ", ".join("[{}]({})".format(source, url)
                                      for url, source in links.items())
                bullets.append("- " + "".join(clause["text"] for clause in clauses)
                               + "（来源：" + citations + "）")
            body = "\n\n".join(bullets) if bullets else "在指定时间窗口内，该分类下没有发现符合条件的新闻。"
            sections.append("**" + category + "**\n\n" + body)
        return "\n\n".join(sections) + "\n"

    def write(self, path):
        Path(path).write_text(self.render(), encoding="utf-8")
