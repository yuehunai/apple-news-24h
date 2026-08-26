"""Project a source page into independently reportable Apple actions.

Projection happens before event reconciliation.  A page can contain several
first-party content releases or product actions; keeping it as one synthetic
article forces every later matcher to choose between losing facts and creating
a mixed event.  This module only projects claims that have their own named
subject and explicit action evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Sequence

from .event_identity import build_event_identity


@dataclass(frozen=True)
class ClaimProjection:
    title: str
    summary: str
    key_facts: tuple[str, ...]
    subject: str
    action: str


_FIRST_PARTY_CONTENT = re.compile(
    r"\b(?:apple\s*tv\+?|apple\s*music|apple\s*arcade|apple\s*books|"
    r"apple\s*podcasts?)\b|苹果\s*(?:tv|音乐|街机|图书|播客)",
    re.I,
)
_CONTENT_ACTION = re.compile(
    r"\b(?P<action>premieres?|premiered|launches?|launched|releases?|released|"
    r"returns?|returned|debuts?|debuted|streams?|streamed|airs?|aired|"
    r"renewed|renewal)\b|"
    r"\b(?:is|are|becomes?|became)\s+(?:now\s+)?(?P<available>available)\b|"
    r"(?P<zh_action>上线|首播|开播|回归|发布|推出|续订|预告|定档|开流)",
    re.I,
)
_CONTENT_OBJECT = re.compile(
    r"\b(?:season\s+\d+|episodes?|movie|film|series|show|documentary|drama|"
    r"comedy|thriller|trailer|teaser)\b|(?:第\s*\d+\s*季|剧集|电影|影片|"
    r"纪录片|喜剧|惊悚剧|预告|先导片)",
    re.I,
)
_MULTI_CONTENT_PAGE = re.compile(
    r"\b(?:two|three|four|five|six|seven|eight|nine|ten|several|multiple|\d{1,2})\b"
    r".{0,60}\b(?:new\s+)?(?:releases?|premieres?|titles?|shows?|films?|movies?|series|projects?)\b|"
    r"\b(?:new|upcoming|coming|multiple|several)\b.{0,45}"
    r"\b(?:releases?|premieres?|lineup|titles?|shows?|films?|movies?|series|projects?)\b|"
    r"(?:两|三|四|五|六|七|八|九|十|多)\s*(?:部|档|个|项|款).{0,30}"
    r"(?:新作|内容|剧集|电影|节目|发布|上线|首播|回归)|"
    r"(?:多部|多档|多项|多款|多部作品|内容阵容).{0,30}(?:发布|上线|首播|回归|定档)",
    re.I,
)
_BACKGROUND_SENTENCE = re.compile(
    r"^(?:after|before|following|based\s+on|inspired\s+by|hailed\s+as|"
    r"according\s+to|since|此前|早前|继|基于|改编自|灵感来自|作为|据)\b|"
    r"\b(?:originally|previously|formerly|\d+\s+(?:days?|weeks?|months?|years?)\s+ago|"
    r"last\s+(?:week|month|year|spring|summer|fall|autumn|winter|"
    r"january|february|march|april|may|june|july|august|september|october|november|december)|"
    r"最初|此前|早前|去年|上个月|上周|\d+\s*(?:天|周|个月|年)前)\b",
    re.I,
)
_NON_SUBJECT_PREFIX = re.compile(
    r"^(?:after|before|following|based|hailed|according|since|in|while|when|if|"
    r"because|although|apple\s*tv\s+today|apple\s*tv|the\s+(?:show|series|movie)|"
    r"this|that|it|此前|早前|继|基于|改编自|据|该(?:剧|片|节目)|这(?:部|档))\b",
    re.I,
)
_LEADING_CHROME = re.compile(
    r"^(?:apple\s*tv\+?|apple\s*music|apple\s*arcade|apple\s*books|"
    r"apple\s*podcasts?)\s*(?:announces?|releases?|has|adds?)?\s*[:：-]?\s*",
    re.I,
)

_APPLE_SILICON_SUBJECT = re.compile(
    r"(?<![a-z0-9])m(?P<generation>\d{1,2})"
    r"(?:\s+(?P<tier>ultra|max|pro))?(?![a-z0-9])",
    re.I,
)
_APPLE_SILICON_RELEASE = re.compile(
    r"\b(?:apple\s+)?(?:announces?|introduces?|launches?|unveils?|debuts?|releases?)\b|"
    r"(?:苹果).{0,30}(?:发布|推出|问世|亮相|登场)",
    re.I,
)


def _clean(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip(" \t\r\n,，;；")


def _sentences(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in re.split(
            r"(?<=[。！？])\s*|(?<=[.!?])\s+|[;；]\s*",
            _clean(value),
        ):
            part = _clean(part)
            key = part.casefold()
            if len(part) < 10 or key in seen:
                continue
            seen.add(key)
            result.append(part)
    return result


def _apple_silicon_subjects(value: str) -> tuple[str, ...]:
    subjects: list[str] = []
    seen: set[str] = set()
    for match in _APPLE_SILICON_SUBJECT.finditer(_clean(value)):
        generation = f"M{match.group('generation')}"
        tier = (match.group("tier") or "").title()
        subject = f"{generation} {tier}".strip()
        key = subject.casefold()
        if key in seen:
            continue
        seen.add(key)
        subjects.append(subject)
    return tuple(subjects)


def project_multi_subject_apple_silicon_claims(
    title: str,
    summary: str,
    key_facts: Sequence[str],
) -> tuple[ClaimProjection, ...]:
    """Project one direct release page onto each named Apple silicon subject.

    A launch page can announce multiple chips, then present unlabeled table rows
    beneath each chip heading.  Keeping the page whole lets rows from one chip
    become mandatory facts for another.  Projection is title-gated and follows
    the ordered subject transitions in the extracted facts; ordinary comparison
    mentions in the body cannot create a projection.
    """
    clean_title = _clean(title)
    title_subjects = _apple_silicon_subjects(clean_title)
    if len(title_subjects) < 2:
        return ()
    if not re.search(r"\bapple\b|苹果", clean_title, re.I):
        return ()
    if not _APPLE_SILICON_RELEASE.search(clean_title):
        return ()
    identity = build_event_identity(title, summary)
    if identity.title_products - {"mac"}:
        return ()

    title_subject_keys = {subject.casefold(): subject for subject in title_subjects}
    assigned: dict[str, list[str]] = {subject: [] for subject in title_subjects}
    seen: dict[str, set[str]] = {subject: set() for subject in title_subjects}
    exclusive_subjects: set[str] = set()
    current_subject = ""

    for sentence in _sentences((summary, *key_facts)):
        mentioned = {
            title_subject_keys[subject.casefold()]
            for subject in _apple_silicon_subjects(sentence)
            if subject.casefold() in title_subject_keys
        }
        if len(mentioned) == 1:
            current_subject = next(iter(mentioned))
            exclusive_subjects.add(current_subject)
            targets = (current_subject,)
        elif len(mentioned) > 1:
            # The shared launch sentence establishes provenance but does not
            # define the active section for following unlabeled specification rows.
            targets = tuple(sorted(mentioned))
            current_subject = ""
        elif current_subject:
            targets = (current_subject,)
        else:
            continue

        for subject in targets:
            key = sentence.casefold()
            if key in seen[subject]:
                continue
            seen[subject].add(key)
            assigned[subject].append(sentence)

    projections: list[ClaimProjection] = []
    for subject in title_subjects:
        facts = assigned[subject]
        # A title-level multi-chip announcement still belongs to every named
        # chip even if a sparse official page has no extracted specification list.
        # When detailed facts exist, require an exclusive subject transition so
        # one shared sentence cannot manufacture two rich child events.
        if facts and subject not in exclusive_subjects:
            facts = []
        projected_summary = next(
            (
                fact
                for fact in facts
                if {
                    title_subject_keys[mentioned.casefold()]
                    for mentioned in _apple_silicon_subjects(fact)
                    if mentioned.casefold() in title_subject_keys
                }
                == {subject}
            ),
            facts[0] if facts else _clean(summary),
        )
        projections.append(
            ClaimProjection(
                title=f"Apple {subject} chip release",
                summary=projected_summary or f"Apple announced the {subject} chip.",
                key_facts=tuple(facts),
                subject=subject,
                action="release",
            )
        )
    return tuple(projections)


def _content_subject(sentence: str, action_match: re.Match[str]) -> str:
    prefix = _LEADING_CHROME.sub("", sentence[: action_match.start()]).strip(" :：,-")
    prefix = re.sub(
        r"^(?:the\s+)?(?:original\s+)?(?:movie|film|series|show|documentary)\s+",
        "",
        prefix,
        flags=re.I,
    )
    prefix = re.sub(r"^(?:电影|剧集|纪录片|节目)\s*", "", prefix)
    # Remove a leading connective left by a compound sentence without touching
    # names that legitimately contain these words.
    prefix = re.sub(r"^(?:and|while|plus|此外|另外|同时)\s+", "", prefix, flags=re.I)
    prefix = _clean(prefix).strip("'\"“”‘’ ")
    if _NON_SUBJECT_PREFIX.search(prefix):
        return ""
    english_words = re.findall(r"[A-Za-z][A-Za-z0-9'’.-]*", prefix)
    if english_words:
        if len(english_words) > 8:
            return ""
        if not any(word[0].isupper() or word.isupper() for word in english_words):
            return ""
    return prefix


def _action_name(match: re.Match[str]) -> str:
    value = (
        match.group("action")
        or match.group("available")
        or match.group("zh_action")
        or ""
    ).casefold()
    if value in {"trailer", "teaser", "预告"}:
        return "trailer-release"
    if value in {"renewed", "renewal", "续订"}:
        return "renewal"
    if value in {"returns", "returned", "回归"}:
        return "return"
    return "release"


def project_first_party_content_claims(
    title: str,
    summary: str,
    key_facts: Sequence[str],
) -> tuple[ClaimProjection, ...]:
    """Return independent named content actions, or no projections.

    The gate is deliberately structural: a first-party content service must be
    present, and at least two sentences must each expose a different named
    subject before an explicit content action.  Plural wording alone never
    triggers a split.
    """
    scope = " ".join((title, summary, *key_facts))
    if not _FIRST_PARTY_CONTENT.search(scope):
        return ()
    if not _MULTI_CONTENT_PAGE.search(_clean(title)):
        return ()
    if re.search(r"apple\s*tv", scope, re.I) and not _CONTENT_OBJECT.search(scope):
        return ()

    projections: list[ClaimProjection] = []
    seen: set[tuple[str, str]] = set()
    for sentence in _sentences((summary, *key_facts)):
        if _BACKGROUND_SENTENCE.search(sentence):
            continue
        action_match = _CONTENT_ACTION.search(sentence)
        if action_match is None:
            continue
        subject = _content_subject(sentence, action_match)
        if not (2 <= len(subject) <= 90):
            continue
        # A date or generic service label is evidence, not a content subject.
        if re.fullmatch(
            r"(?:apple\s*tv\+?|apple\s*music|apple\s*arcade|apple\s*books|"
            r"apple\s*podcasts?|the\s+(?:show|series|movie)|它|该(?:剧|片|节目))",
            subject,
            re.I,
        ):
            continue
        action = _action_name(action_match)
        key = (subject.casefold(), action)
        if key in seen:
            continue
        seen.add(key)
        label = "Apple TV" if re.search(r"apple\s*tv|苹果\s*tv", scope, re.I) else "Apple service"
        verb = {
            "release": "release",
            "return": "return",
            "renewal": "renewal",
            "trailer-release": "trailer release",
        }[action]
        projections.append(
            ClaimProjection(
                title=f"{label} '{subject}' {verb}",
                summary=sentence,
                key_facts=(sentence,),
                subject=subject,
                action=action,
            )
        )

    if len({projection.subject.casefold() for projection in projections}) < 2:
        return ()
    return tuple(projections)
