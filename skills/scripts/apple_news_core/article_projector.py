"""Project a source page into independently reportable Apple actions.

Projection happens before event reconciliation.  A page can contain several
first-party content releases or product actions; keeping it as one synthetic
article forces every later matcher to choose between losing facts and creating
a mixed event.  This module only projects claims that have their own named
subject and explicit action evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
import unicodedata
from typing import Iterable, Sequence

from .event_identity import _compiled_rule, disclosed_device_subjects, high_confidence_direct_apple_action, iphone_report_subjects, EventIdentity, build_event_identity, bind_article_claims, rollout_language_names, source_sentence_spans, is_os_release_announcement, source_disclosure_bundle, source_editorial_outlook, source_dated_launch_frame, source_leadership_interview_frame, source_operation_frame, source_executive_government_frame, source_executive_people, source_denies_action, source_device_operation_frame, source_editorial_evaluation, source_apple_invitation_fact
from .models import ArticleEvidence, BoundClaim
from .event_identity import bind_source_report
from .article_processing import editorial_list_unit_ids, release_history_unit_ids, inline_media_marker_spans, clean_sentence, clean_fact_text, score_terms, add_unique_text, roundup_title_from_item


@dataclass(frozen=True)
class ClaimProjection:
    title: str
    summary: str
    key_facts: tuple[str, ...]
    subject: str
    action: str
    claim: BoundClaim | None = None


_FIRST_PARTY_CONTENT = _compiled_rule(r"\b(?:apple\s*tv\+?|apple\s*music|apple\s*arcade|apple\s*books|"
    r"apple\s*podcasts?)\b|苹果\s*(?:tv|音乐|街机|图书|播客)", re.I)
_CONTENT_ACTION = _compiled_rule(r"\b(?P<action>premieres?|premiered|launches?|launched|releases?|released|"
    r"returns?|returned|debuts?|debuted|streams?|streamed|airs?|aired|"
    r"renewed|renewal)\b|"
    r"\b(?:is|are|becomes?|became)\s+(?:now\s+)?(?P<available>available)\b|"
    r"(?P<zh_action>上线|首播|开播|回归|发布|推出|续订|预告|定档|开流)", re.I)
_CONTENT_OBJECT = _compiled_rule(r"\b(?:season\s+\d+|episodes?|movie|film|series|show|documentary|drama|"
    r"comedy|thriller|trailer|teaser)\b|(?:第\s*\d+\s*季|剧集|电影|影片|"
    r"纪录片|喜剧|惊悚剧|预告|先导片)", re.I)
_MULTI_CONTENT_PAGE = _compiled_rule(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|several|multiple|\d{1,2})\b"
    r".{0,60}\b(?:new\s+)?(?:releases?|premieres?|titles?|shows?|films?|movies?|series|specials?|projects?)\b|"
    r"\b(?:new|upcoming|coming|multiple|several)\b.{0,45}"
    r"\b(?:releases?|premieres?|lineup|titles?|shows?|films?|movies?|series|specials?|projects?)\b|"
    r"(?:两|三|四|五|六|七|八|九|十|多)\s*(?:部|档|个|项|款).{0,30}"
    r"(?:新作|内容|剧集|电影|节目|发布|上线|首播|回归)|"
    r"(?:多部|多档|多项|多款|多部作品|内容阵容).{0,30}(?:发布|上线|首播|回归|定档)", re.I)
_BACKGROUND_SENTENCE = _compiled_rule(r"^(?:after|before|following|based\s+on|inspired\s+by|hailed\s+as|"
    r"according\s+to|since|此前|早前|继|基于|改编自|灵感来自|作为|据)\b|"
    r"\b(?:originally|previously|formerly|\d+\s+(?:days?|weeks?|months?|years?)\s+ago|"
    r"last\s+(?:week|month|year|spring|summer|fall|autumn|winter|"
    r"january|february|march|april|may|june|july|august|september|october|november|december)|"
    r"最初|此前|早前|去年|上个月|上周|\d+\s*(?:天|周|个月|年)前)\b", re.I)
_NON_SUBJECT_PREFIX = _compiled_rule(r"^(?:after|before|following|based|hailed|according|since|in|while|when|if|"
    r"because|although|apple\s*tv\s+today|apple\s*tv|the\s+(?:show|series|movie)|"
    r"this|that|it|此前|早前|继|基于|改编自|据|该(?:剧|片|节目)|这(?:部|档))\b", re.I)
_LEADING_CHROME = _compiled_rule(r"^(?:apple\s*tv\+?|apple\s*music|apple\s*arcade|apple\s*books|"
    r"apple\s*podcasts?)\s*(?:announces?|releases?|has|adds?)?\s*[:：-]?\s*", re.I)

_APPLE_SILICON_SUBJECT = _compiled_rule(r"(?<![a-z0-9])m(?P<generation>\d{1,2})"
    r"(?:\s+(?P<tier>ultra|max|pro))?(?![a-z0-9])", re.I)
_APPLE_SILICON_RELEASE = _compiled_rule(r"\b(?:apple\s+)?(?:announces?|introduces?|launches?|unveils?|debuts?|releases?)\b|"
    r"(?:苹果).{0,30}(?:发布|推出|问世|亮相|登场)", re.I)


def _clean(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\u00a0", " ")
    return _compiled_rule(r"\s+", 0).sub(" ", value, 0).strip(" \t\r\n,，;；")


def _sentences(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in _compiled_rule(r"(?<=[。！？])\s*|(?<=[.!?])\s+|[;；]\s*", 0).split(_clean(value), 0):
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
    if not _compiled_rule(r"\bapple\b|苹果", re.I).search(clean_title):
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
    prefix = _compiled_rule(r"^(?:today|now|currently|this\s+(?:week|month|year)|"
        r"今日|今天|目前|本(?:周|月|年))\s*[,，:：-]?\s*", re.I).sub("", prefix, 0)
    prefix = _compiled_rule(r"^(?:the\s+)?(?:original\s+)?(?:movie|film|series|show|documentary)\s+", re.I).sub("", prefix, 0)
    prefix = _compiled_rule(r"^(?:电影|剧集|纪录片|节目)\s*", 0).sub("", prefix, 0)
    # Remove a leading connective left by a compound sentence without touching
    # names that legitimately contain these words.
    prefix = _compiled_rule(r"^(?:and|while|plus|此外|另外|同时)\s+", re.I).sub("", prefix, 0)
    prefix = _clean(prefix).strip("'\"“”‘’ ")
    if _NON_SUBJECT_PREFIX.search(prefix):
        return ""
    english_words = _compiled_rule(r"[A-Za-z][A-Za-z0-9'’.-]*", 0).findall(prefix)
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
    if not _FIRST_PARTY_CONTENT.search(title + ' ' + summary[:350]):
        return ()
    if not _MULTI_CONTENT_PAGE.search(_clean(title)):
        return ()
    if _compiled_rule(r"apple\s*tv", re.I).search(scope) and not _CONTENT_OBJECT.search(scope):
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
        possessive_installment = _compiled_rule(r"\s+(?:its|the)\s+(season\s+\d+\s+(?:finale|premiere))\b", re.I).match(sentence[action_match.end() :])
        if subject and possessive_installment:
            subject = f"{subject} {possessive_installment.group(1)}"
        subject = _compiled_rule(r"(?i)(\S+)[’']s\s+(season\s+\d+\s+(?:finale|premiere))$", 0).sub(r"\1 \2", subject, 0)
        if not (2 <= len(subject) <= 90):
            continue
        # A date or generic service label is evidence, not a content subject.
        if _compiled_rule(r"(?:apple\s*tv\+?|apple\s*music|apple\s*arcade|apple\s*books|"
            r"apple\s*podcasts?|the\s+(?:show|series|movie)|它|该(?:剧|片|节目))", re.I).fullmatch(subject):
            continue
        action = _action_name(action_match)
        key = (subject.casefold(), action)
        if key in seen:
            continue
        seen.add(key)
        label = "Apple TV" if _compiled_rule(r"apple\s*tv|苹果\s*tv", re.I).search(scope) else "Apple service"
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


def project_content_source_sections(
    evidence: ArticleEvidence, title: str, summary: str, *, fact_limit: int,
) -> list[tuple[str, str, list[str]]]:
    """Bind independently announced works to their own source sections."""
    if (not _FIRST_PARTY_CONTENT.search(f"{title} {summary}")
            or not _MULTI_CONTENT_PAGE.search(_clean(title))):
        return []
    quote = _compiled_rule(r'“([^”]{2,90})”|‘((?:[^’]|(?<=\w)’(?=\w)){2,90})’(?!\w)|'
        r'"([^"\n]{2,90})"|(?<!\w)\'((?:[^\']|(?<=\w)\'(?=\w)){2,90})\'(?!\w)', 0)
    sections: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    current = ""
    announced: set[str] = set()
    for unit in evidence.units:
        if unit.kind not in {"h2", "h3", "li", "p"} or unit.container_id == "caption":
            continue
        text = unit.text.strip()
        quoted = [next(part for part in match.groups() if part) for match in quote.finditer(text)]
        heading = unit.kind in {"h2", "h3"} and len(quoted) == 1
        list_release = unit.kind == "li" and bool(quoted) and bool(_compiled_rule(r"\b(?:will\s+)?(?:debut|follow|premiere|release|stream)\b|首播|上线|发布", re.I).search(text))
        named_film = (_compiled_rule(r"\b(?:film|movie|series|special)\s+"
            r"(?P<name>[A-Z][A-Za-z0-9'’:&-]+(?:\s+(?:of|the|a|an|[A-Z][A-Za-z0-9'’:&-]+)){1,7})"
            r"(?=[.!?])", 0).search(text)
            if unit.kind == "p" and _compiled_rule(r"\b(?:premier|debut|release|spotlight)", re.I).search(text)
            else None)
        if heading or list_release or named_film:
            name = quoted[0] if heading or list_release else named_film.group("name")
            name = name.strip(" \"'“”‘’.,;:!? ")
            current = _compiled_rule(r"\s+", 0).sub(" ", name, 0).casefold()
            names.setdefault(current, name)
            sections.setdefault(current, [])
            if list_release or named_film:
                announced.add(current)
        elif unit.kind in {"h2", "h3"}:
            current = ""
            continue
        if not current or unit.kind in {"h2", "h3"}:
            continue
        # A recommendation, subscription pitch, image credit or a newly named
        # neighboring work ends the active section; it is not this work's fact.
        if (_compiled_rule(r"^(?:if\s+you|beyond\s+this|additional\s+.+recommend)\b", re.I).match(text)
                or _compiled_rule(r"\b(?:check\s+out|free\s+trial|image\s+credit|subscribe)\b", re.I).search(text)
                or (quote.match(text) and quoted
                    and all(name.casefold() != current for name in quoted))):
            current = ""
            continue
        if len(quoted) > 1 or _compiled_rule(r"\b(?:each|both)\s+new\s+(?:film|special)\b", re.I).search(text):
            continue
        if named_film:
            # The announcement and its date are source facts; the writer's
            # general seasonal opinion in the following sentence is not.
            parts = list(source_sentence_spans(text))
            for start, end in parts[:2]:
                sections[current].append(text[start:end])
        else:
            sections[current].append(text)
        if _compiled_rule(r"\b(?:will\s+)?(?:debut|follow|premiere|release|stream)s?\b|首播|上线|发布", re.I).search(text):
            announced.add(current)
    ready = [key for key in sections if key in announced and sections[key]]
    if len(ready) < 2:
        return []
    return [(f"Apple TV '{names[key]}' release", " ".join(sections[key][:5]),
             sections[key][:fact_limit]) for key in ready]



def project_article_evidence(evidence: ArticleEvidence, *, claims: tuple[BoundClaim, ...] | None = None) -> tuple[tuple[ClaimProjection, ...], tuple[tuple[str, int, int], ...], tuple[tuple[str, int, int, str], ...]]:
    """Return owned projections and the exact unprocessed source unit ids."""
    units = {unit.unit_id: unit for unit in evidence.units}
    projections = []
    for claim in bind_article_claims(evidence) if claims is None else claims:
        if claim.object == "languages":
            index = next(i for i, unit in enumerate(evidence.units) if unit.unit_id == claim.unit_ids[-1])
            following = []
            if units[claim.unit_ids[-1]].text.rstrip().endswith((":", "：")):
                for unit in evidence.units[index + 1:]:
                    if unit.kind != "li":
                        break
                    following.append(unit)
            if following:
                names = [name for unit in following for name in rollout_language_names(unit.text)]
                qualifiers = tuple((name, *qualifier[1:]) for qualifier in claim.qualifiers
                                   for name in (names if qualifier[0] == "additional-languages" and names else [qualifier[0]]))
                claim = replace(claim, qualifiers=qualifiers, unit_ids=claim.unit_ids + tuple(unit.unit_id for unit in following),
                    evidence_spans=claim.evidence_spans + tuple((unit.unit_id, 0, len(unit.text)) for unit in following))
        facts = tuple(units[key].text[start:end] for key, start, end in claim.evidence_spans)
        summary = facts[0] if facts else ""
        title = evidence.title if not facts or claim.action in {"document-publication", "plan-launch", "feature-rollout", "web-exploit-campaign", "cpu-benchmark-report", "platform-capability-inventory-report", "app-capability-inventory-report", "app-publisher-chart-report", "media-invitation", "leadership-report"} else summary
        if claim.action == 'reported-launch-plan':
            title = claim.subject.replace('-', ' ') + ' launch report'
        projections.append(ClaimProjection(title, summary, facts,
                                          claim.subject, claim.action, claim))
    assigned = [span for projection in projections for span in projection.claim.evidence_spans]
    remaining, excluded = source_evidence_remainder(evidence, assigned)
    return tuple(projections), tuple(remaining), tuple(excluded)



def project_reportable_evidence(evidence: ArticleEvidence) -> tuple[tuple[ClaimProjection, ...], tuple[tuple[str, int, int], ...], tuple[tuple[str, int, int, str], ...]]:
    """Choose event projections while keeping a release's feature inventory whole.

    Local claim extraction remains available through project_article_evidence;
    those subordinate claims must not replace the source's primary release.
    """
    report = bind_source_report(evidence)
    if report is not None:
        return project_article_evidence(evidence, claims=report)
    device = source_device_operation_frame(evidence.title, evidence.raw_lead)
    if is_os_release_announcement(evidence.title) or (device and device.action == "device-announcement"):
        remaining, excluded = source_evidence_remainder(evidence, [])
        return (), tuple(remaining), tuple(excluded)
    return project_article_evidence(evidence)


def single_article_input_projection(evidence: ArticleEvidence) -> ClaimProjection | None:
    """Bind one fully supported input action; ambiguity retains the source profile."""
    from .event_matcher import identity_pair_decision
    # Sparse input lacks the surrounding text needed to interpret negation or
    # corrections. It must not promote an affirmative substring into a claim.
    if any(_compiled_rule(r"\b(?:not|never|denies?|without)\b|不会|并非|不支持|不提供|否认|尚未", re.I).search(unit.text)
           for unit in evidence.units):
        return None
    # The current local binders do not encode OS version qualifiers. Retain
    # the existing version-aware source profile instead of erasing that limit.
    if any(_compiled_rule(r"\b(?:iOS|iPadOS|macOS|watchOS|visionOS|tvOS)\s*\d", re.I).search(unit.text)
           for unit in evidence.units):
        return None
    projections, remaining, _ = project_article_evidence(evidence)
    if not projections or remaining:
        return None
    first = projections[0]
    if any(identity_pair_decision(left.claim, right.claim) != 'match'
           for index, left in enumerate(projections) for right in projections[index + 1:]):
        return None
    claim = replace(first.claim,
        qualifiers=tuple(dict.fromkeys(q for item in projections for q in item.claim.qualifiers)),
        unit_ids=tuple(dict.fromkeys(key for item in projections for key in item.claim.unit_ids)),
        evidence_spans=tuple(dict.fromkeys(span for item in projections for span in item.claim.evidence_spans)))
    return replace(first, claim=claim,
                   key_facts=tuple(fact for item in projections for fact in item.key_facts))


def source_evidence_remainder(evidence: ArticleEvidence, assigned):
    remaining = []
    excluded = []
    editorial_units = editorial_list_unit_ids(evidence)
    history_units = release_history_unit_ids(evidence)
    for unit in evidence.units:
        if unit.unit_id in editorial_units:
            excluded.append((unit.unit_id, 0, len(unit.text), "Publisher programme credits or subscription navigation"))
            continue
        intervals = [(start, end) for key, start, end in assigned if key == unit.unit_id]
        # Recognize complete URL markers before punctuation splits their query
        # string. Keep the original unit and exact excluded source interval.
        for start, end in inline_media_marker_spans(unit.text):
            if not any(left < end and start < right for left, right in intervals):
                intervals.append((start, end))
                excluded.append((unit.unit_id, start, end, "Serialized inline media URL metadata"))
        intervals.sort()
        cursor = 0
        gaps = []
        for start, end in intervals:
            if cursor < start:
                gaps.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < len(unit.text):
            gaps.append((cursor, len(unit.text)))
        for start, end in gaps:
            if unit.unit_id in history_units:
                excluded.append((unit.unit_id, start, end, "Explicit release-history appendix, not current release requirements"))
                continue
            # A narrator's forecast before an independently bound report is
            # not part of that reporter's claim. Keep the original evidence,
            # but do not require consumption to turn it back into source news.
            author_prediction = (unit.kind == 'p' and start == 0
                and any(key == unit.unit_id and owned_start == end for key, owned_start, _ in assigned)
                # Postposed attribution can make first-person language a
                # source's commitment even without quotation marks.
                and not _compiled_rule(
                    r"\b(?:according\s+to|[a-z][a-z0-9'’-]*\s+"
                    r"(?:said|says|stated|states|told|wrote|writes|announced|announces))\b",
                    re.I).search(unit.text[start:end])
                and _compiled_rule(
                    r"\s*(?:what\s+)?(?:we|I)\s+(?:(?:probably|perhaps|likely)\s+|"
                    r"(?:expect|think|believe|suspect|predict|anticipate)\b)"
                    r"[^.!?。！？\"“”]*", re.I).fullmatch(unit.text[start:end]))
            if author_prediction:
                excluded.append((unit.unit_id, start, end,
                    "Editorial inference: first-person author prediction, not the adjacent attributed report"))
                continue
            separator = bool(_compiled_rule(r"[\s,，;；。.!！？?、]+", 0).fullmatch(unit.text[start:end]))
            if separator or unit.kind == "h1":
                reason = "Source punctuation/whitespace separator" if separator else "Parent heading retained as context, not an independent action"
                excluded.append((unit.unit_id, start, end, reason))
            else:
                left, right = start, end
                while left < right and unit.text[left].isspace():
                    left += 1
                while right > left and unit.text[right - 1].isspace():
                    right -= 1
                if left > start:
                    excluded.append((unit.unit_id, start, left, "Whitespace separator"))
                if right < end:
                    excluded.append((unit.unit_id, right, end, "Whitespace separator"))
                cursor = left
                for local_start, local_end in source_sentence_spans(unit.text[left:right]):
                    start, end = left + local_start, left + local_end
                    if cursor < start:
                        excluded.append((unit.unit_id, cursor, start, "Whitespace separator"))
                    reason = _unprocessed_context_reason(evidence.title, unit.text[start:end], unit.text)
                    if reason:
                        excluded.append((unit.unit_id, start, end, reason))
                    else:
                        remaining.append((unit.unit_id, start, end))
                    cursor = end
                if cursor < right:
                    excluded.append((unit.unit_id, cursor, right, "Whitespace separator"))
    return tuple(remaining), tuple(excluded)


def _unprocessed_context_reason(parent_title: str, text: str, unit_text: str) -> str:
    if _compiled_rule(r"\s*(?:Here are the details|Here(?:['’]s| is) what the company says)[.!:]?\s*", re.I).fullmatch(text):
        return "Editorial transition to the details already retained from the source"
    if _compiled_rule(r"\s*For\s+.{1,120}full coverage of\s+.{1,220},\s*follow this link[.!]?\s*", re.I).fullmatch(text):
        return "Navigation to the publisher's event coverage, not a source action"
    delay_overview = bool(_compiled_rule(r"features?.*(?:delay|not.*launch|later)|功能.*(?:不随|分批|延期|延迟|推迟|首发)", re.I).search(parent_title))
    if not delay_overview:
        return ""
    if (_compiled_rule(r"(?:用于|used to).*(?:展示|showcase).*(?:游戏性能|gaming performance)", re.I).search(text)
        and not _compiled_rule(r"Apple\s*Arcade|苹果街机", re.I).search(text)):
        return "Third-party game used as a hardware demonstration; no independent Apple action"
    if (_compiled_rule(r"preorders?|ship(?:ping|ment)?|预购|发货|送至用户", re.I).search(unit_text)
        and _compiled_rule(r"iPhone|Apple Watch|AirPods|该机|产品", re.I).search(text)
        and not _compiled_rule(r"feature|功能|OTA|支持", re.I).search(text)):
        return "Hardware sale schedule is background to this feature-delay overview"
    if len(set(_compiled_rule(r"\b(?:iOS|iPadOS|watchOS|macOS|tvOS|visionOS)\b", re.I).findall(text))) >= 3:
        return "Operating-system release wave is background to the independently delayed features"
    if _compiled_rule(r"部分软件功能|相关功能则并非全部同步|兼容设备的用户无需购买新硬件", 0).search(text):
        return "Parent overview context without an independent named action"
    return ""


def project_numbered_service_announcements(
    title: str,
    summary: str,
    key_facts: list[str],
    *, identity: EventIdentity, fact_limit: int,
) -> list[tuple[str, str, list[str]]]:
    """Split an explicitly numbered first-party service announcement into actions."""
    service_products = identity.title_products & {
        "apple-arcade",
        "apple-books",
        "apple-music",
        "apple-sports",
        "apple-tv",
    }
    hardware_products = identity.title_products & {
        "airpods",
        "apple-watch",
        "homepod",
        "imac",
        "ipad",
        "ipad-air",
        "ipad-mini",
        "ipad-pro",
        "iphone",
        "mac",
        "mac-mini",
        "mac-pro",
        "mac-studio",
        "macbook",
        "vision-pro",
    }
    explicit_numbered_announcement = bool(
        _compiled_rule(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\b"
            r".{0,45}\b(?:new\s+)?(?:films?|games?|movies?|projects?|series|shows?|titles?)\b|"
            r"(?:两|三|四|五|六|七|八|九|十|\d+)\s*(?:部|款|项)"
            r".{0,24}(?:电影|游戏|剧集|节目|作品|内容)", 0).search(title.lower())
    )
    if (
        identity.scope != "apple-direct"
        or len(service_products) != 1
        or hardware_products
        or not explicit_numbered_announcement
    ):
        return [(title, summary, key_facts)]
    groups: list[tuple[str, list[str]]] = []
    for fact in key_facts:
        cleaned = clean_sentence(fact)
        header = _compiled_rule(r"^#?\s*(\d+)\s*[:：.)、-]\s*(.+)$", 0).match(cleaned)
        if header:
            groups.append((clean_sentence(header.group(2)), []))
        elif groups and cleaned:
            groups[-1][1].append(cleaned)
    if len(groups) < 2:
        return [(title, summary, key_facts)]
    variants: list[tuple[str, str, list[str]]] = []
    for heading, details in groups:
        facts = [heading, *details]
        variants.append((heading, " ".join(facts[:6]), facts[:fact_limit]))
    return variants



def project_title_content_announcements(
    title: str,
    summary: str,
    key_facts: list[str],
    *, identity: EventIdentity, fact_limit: int, trailer_evidence: bool,
) -> list[tuple[str, str, list[str]]]:
    """Split title-level announcements for distinct first-party content works."""
    original = [(title, summary, key_facts)]
    service_labels = {
        "apple-tv": "Apple TV",
        "apple-music": "Apple Music",
        "apple-arcade": "Apple Arcade",
        "apple-books": "Apple Books",
        "apple-sports": "Apple Sports",
    }
    service_product = next(
        (product for product in service_labels if product in identity.title_products),
        "",
    )
    if identity.scope != "apple-direct" or not service_product:
        return original

    announcements: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_announcement(name: str, action: str) -> None:
        cleaned = clean_sentence(name).strip(" .,:;!?()[]{}\"'“”‘’—-")
        cleaned = _compiled_rule(r"(?i)^(?:its|the|a|an)\s+", 0).sub("", cleaned, 0)
        cleaned = _compiled_rule(r"(?i)^(?:epic|new|upcoming|original)\s+", 0).sub("", cleaned, 0)
        cleaned = _compiled_rule(r"(?i)\s+adaptation$", 0).sub("", cleaned, 0).strip()
        if not cleaned or len(cleaned) > 70 or len(cleaned.split()) > 8:
            return
        if cleaned.lower() in {
            "apple tv",
            "apple music",
            "apple arcade",
            "apple books",
            "apple sports",
        }:
            return
        key = (cleaned.lower(), action)
        if key not in seen:
            announcements.append((cleaned, action))
            seen.add(key)

    release_patterns = (
        r"(?i:\b(?:streaming|premiere|release)\s+date\s+for\s+)"
        r"(?P<name>(?:(?:its|the)\s+)?(?:(?:epic|new|upcoming|original)\s+)?"
        r"[A-Z][A-Za-z0-9'’:+.-]*(?:\s+[A-Z][A-Za-z0-9'’:+.-]*){0,6}?)"
        r"(?i:\s+adaptation)?(?=,|;|\s+(?:and|plus)\s+|$)",
        r"(?P<name>[A-Z][A-Za-z0-9'’:+.-]*(?:\s+[A-Z][A-Za-z0-9'’:+.-]*){0,6}?)"
        r"(?i:\s+(?:streaming|premiere|release)\s+date)\b",
    )
    for pattern in release_patterns:
        for match in re.finditer(pattern, title):
            add_announcement(match.group("name"), "release-date")

    trailer_patterns = (
        r"(?i:\bnew\s+)(?P<names>[^,;:]{2,100}?)(?i:\s+trailers?)\b",
        r"(?i:\btrailers?\s+for\s+)(?P<names>[^,;:]{2,100}?)(?=,|;|$)",
    )
    for pattern in trailer_patterns:
        for match in re.finditer(pattern, title):
            # A quoted work inside a service phrase is the title. Splitting
            # that phrase on apostrophes manufactures another "work".
            if _compiled_rule(r"[‘“\"']", 0).search(match.group("names")):
                continue
            names = _compiled_rule(r"\s+(?:and|&)\s+|\s*,\s*", re.I).split(match.group("names"), 0)
            for name in names:
                add_announcement(name, "trailer")
    if trailer_evidence:
        for quoted in _compiled_rule(r'“([^”]{2,70})”|‘((?:[^’]|(?<=\w)’(?=\w)){2,70})’(?!\w)|'
            r'"([^"\n]{2,70})"|(?<!\w)\'((?:[^\']|(?<=\w)\'(?=\w)){2,70})\'(?!\w)', 0).finditer(title):
            add_announcement(next(part for part in quoted.groups() if part), "trailer")

    if len({name.lower() for name, _ in announcements}) < 2:
        return original

    sentences = [clean_sentence(value[start:end]) for value in [*key_facts, summary]
                 for start, end in source_sentence_spans(value) if clean_sentence(value[start:end])]
    service_label = service_labels[service_product]
    variants: list[tuple[str, str, list[str]]] = []
    for name, action in announcements:
        related = [sentence for sentence in sentences if name.lower() in sentence.lower()]
        if not related:
            related = [clean_sentence(summary) or title]
        variant_title = (
            f"{service_label} announces {name} streaming date"
            if action == "release-date"
            else f"{service_label} releases {name} trailer"
        )
        variants.append((variant_title, " ".join(related[:5]), related[:fact_limit]))
    return variants



def project_compound_product_actions(
    title: str,
    summary: str,
    key_facts: list[str],
    *, identity: EventIdentity, headline_identity: EventIdentity,
    fact_identities: Iterable[EventIdentity], fact_limit: int,
) -> list[tuple[str, str, list[str]]]:
    """Project a multi-action product report onto the concrete actions it establishes."""
    generations = sorted(
        component.removeprefix("product-generation:")
        for component in identity.components
        if component.startswith("product-generation:")
    )
    if len(generations) != 1 or identity.scope != "apple-direct":
        return [(title, summary, key_facts)]
    headline_actions = sum(
        [
            "production-ramp" in headline_identity.components,
            "product-release-delay" in headline_identity.components,
            "camera-system" in headline_identity.components,
            "price-change" in headline_identity.actions,
        ]
    )
    if headline_actions < 2:
        return [(title, summary, key_facts)]
    product_label = generations[0].replace("iphone-", "iPhone ").replace("ipad-", "iPad ")
    groups: dict[str, list[str]] = {
        "production": [],
        "delay": [],
        "camera": [],
        "price": [],
    }
    for fact, fact_identity in zip(key_facts, fact_identities):
        cleaned = clean_sentence(fact)
        if not cleaned:
            continue
        if "production-ramp" in fact_identity.components:
            groups["production"].append(cleaned)
        if "product-release-delay" in fact_identity.components:
            groups["delay"].append(cleaned)
        if "camera-system" in fact_identity.components:
            groups["camera"].append(cleaned)
        if "price-change" in fact_identity.actions:
            groups["price"].append(cleaned)
    groups = {name: facts for name, facts in groups.items() if facts}
    if len(groups) < 2:
        return [(title, summary, key_facts)]
    titles = {
        "production": f"Apple {product_label} production ramp",
        "delay": f"Apple {product_label} release delay",
        "camera": f"Apple {product_label} variable-aperture camera update",
        "price": f"Apple {product_label} price change report",
    }
    return [
        (titles[name], " ".join(facts[:6]), facts[:fact_limit])
        for name, facts in groups.items()
    ]



def project_roundup_items(title: str, summary: str, key_facts: list[str], *,
                         parent_is_roundup: bool, items: Sequence[tuple[str, str, str]]) -> list[tuple[str, str, list[str]]]:
    """Project only source-supported local items of an explicit roundup."""
    if not parent_is_roundup or len(key_facts) <= 1:
        return [(title, summary, key_facts)]
    variants = [(item_title, text, [text]) for item_title, text, source_tier in items
                if source_tier in {"strong", "ecosystem"}]
    return variants or [(title, summary, key_facts)]


def adjacent_unattributed_prediction_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Review a possible new forecast instead of inheriting a prior speaker.

    This does not classify the sentence as opinion or remove its evidence.
    Quoted continuations and forecasts with their own attribution stay bound.
    """
    parts = tuple(source_sentence_spans(text))
    attribution = _compiled_rule(
        r'\b(?:says?|said|reports?|reported|according\s+to|told|states?|stated|'
        r'writes?|wrote|announces?|announced)\b|'
        r'\b(?:the\s+)?(?:report|company|source|outlet)\s+(?:adds?|expects?|predicts?)\b|'
        r'据.{0,35}(?:报道|透露|称)|(?:报道|消息|报告|该公司|该媒体).{0,12}(?:称|表示|预计|补充)|表示|透露', re.I)
    prediction = _compiled_rule(
        r'\b(?:may|might|could)\s+(?:(?:still|also|yet|potentially)\s+)*'
        r'(?:be\s+(?:announced|unveiled|released|shipped|shown\s+(?:off|tomorrow|this|next|later|earlier))\b|go\s+on\s+sale\b|'
        r'(?:ship|arrive|launch)\s+(?:tomorrow|this|next|later|earlier|in\s+stores)\b)|'
        r'(?:它们|这些(?:设备|产品)|这款(?:设备|产品)|该(?:设备|产品)).{0,8}'
        r'(?:可能|也许|或许).{0,8}(?:上市|发售|发货|亮相|(?:提前|公开)展示)', re.I)
    result = []
    for index, (start, end) in enumerate(parts[1:], start=1):
        prior = text[slice(*parts[index - 1])]
        current = text[start:end]
        if not (attribution.search(prior) and prediction.search(current)) or attribution.search(current):
            continue
        prefix = text[:start]
        if (prefix.count('“') > prefix.count('”') or prefix.count('‘') > prefix.count('’')
                or prefix.count('"') % 2
                or len(_compiled_rule(r"(?<!\w)'|'(?!\w)", 0).findall(prefix)) % 2
                or _compiled_rule(r'\b(?:if|unless|depending)\b|如果|只要|除非', re.I).search(current)):
            continue
        result.append((start, end))
    return tuple(result)


def project_sectioned_home_preview(evidence: ArticleEvidence, fact_limit: int) -> list[tuple[str, str, list[str]]]:
    """Use explicit device sections, never a borrowed UI or silicon name.

    Only paragraphs within a recognized section may inherit its owner. Short
    list items require that section's explicit enumeration introduction.
    """
    s = lambda pattern, text: _compiled_rule(pattern, re.I).search(text)
    if not (s(r'products?|产品|新品', evidence.title)
            and s(r'what\s+to\s+expect|发布|新品', evidence.raw_lead)
            and s(r'smart\s*(?:home|hub)|智能家居', evidence.raw_lead)):
        return []
    groups: dict[str, list[str]] = {}
    owner = None
    enumeration = False
    labels = {'apple-home-hub': 'Apple smart home hub device disclosure',
              'apple-tv': 'Apple TV 4K hardware configuration disclosure',
              'homepod-mini': 'Apple HomePod mini device disclosure',
              'accessories': 'Apple smart home accessories partnership disclosure',
              'surround': 'Apple TV and HomePod surround sound software feature report'}
    for unit in evidence.units:
        text = unit.text
        if unit.kind in {'h2', 'h3'}:
            owner = None
            enumeration = False
            if unit.kind == 'h3':
                if s(r'smart\s*(?:display|hub)|智能.{0,5}(?:屏|中枢)', text): owner = 'apple-home-hub'
                elif s(r'apple\s*tv', text): owner = 'apple-tv'
                elif s(r'homepod\s*mini', text): owner = 'homepod-mini'
                elif s(r'second.party|联合开发', text): owner = 'accessories'
            continue
        if not owner or unit.kind not in {'p', 'li'}:
            continue
        if unit.kind == 'li':
            if enumeration and len(text.split()) <= 4 and not s(r'https?://|[。.!?]', text):
                groups.setdefault(owner, []).append(text)
            continue
        enumeration = bool(s(r'(?:colors?|配色)\s*[:：]$', text))
        current = owner
        if (owner == 'apple-tv' and s(r'software\s+features?|软件功能', text)
                and s(r'surround\s+sound|环绕声', text) and s(r'code\s+references?|代码', text)):
            current = 'surround'
        uncertain = adjacent_unattributed_prediction_spans(text)
        # A paragraph's product owner does not establish the speaker of every
        # sentence. Unbound predictions remain available in source review.
        facts = [text[a:b] for a, b in source_sentence_spans(text)
                 if (a, b) not in uncertain] if uncertain else [text]
        groups.setdefault(current, []).extend(facts)
    # Require independently reported details, not merely a linked contents list.
    if len(groups) < 2 or any(not any(s(r'report|bloomberg|gurman|透露|据|彭博', p) for p in facts)
                              for facts in groups.values()):
        return []
    return [(labels[owner], ' '.join(facts[:4]), facts[:fact_limit]) for owner, facts in groups.items()]


def project_smart_home_roadmap(
    title: str,
    summary: str,
    key_facts: list[str],
    *, fact_limit: int, evidence: ArticleEvidence | None = None,
) -> list[tuple[str, str, list[str]]]:
    """Project a genuine multi-product smart-home roadmap into product actions."""
    original = [(title, summary, key_facts)]
    if evidence is not None:
        sectioned = project_sectioned_home_preview(evidence, fact_limit)
        if sectioned:
            return sectioned
    title_lower = title.lower()
    # A retail-layout, merchandising, or launch-preparation report has one
    # operational predicate. Product roadmaps in its background explain the
    # operation; they are not independent claims owned by that source page.
    retail_operation = bool(
        _compiled_rule(r"\b(?:apple\s+)?(?:retail\s+)?stores?\b.{0,65}"
            r"(?:prepar|rearrang|layout|display|merchandis|refresh|receive.{0,25}boxes)|"
            r"\b(?:layout|display|merchandis)\b.{0,45}\b(?:stores?|retail)\b|"
            r"(?:苹果)?零售店.{0,40}(?:准备|调整|重组|改版|布局|陈列|展区)|"
            r"(?:布局|陈列|展区|宣传物料).{0,30}(?:零售店|门店|apple store)", re.I).search(title_lower)
    )
    if retail_operation:
        return original
    opening = evidence.raw_lead if evidence is not None else summary[:600]
    current_paragraph_report = bool(evidence is not None
        and _compiled_rule(r'苹果(?:公司)?.{0,20}(?:将于|计划|即将|预计).{0,25}发布.{0,12}(?:一系列|多款).{0,12}智能家居|'
            r'Apple.{0,20}(?:will|plans?\s+to).{0,25}(?:announce|unveil|launch).{0,20}(?:lineup|several|multiple).{0,20}(?:smart.home|home)', re.I).search(opening)
        and not _compiled_rule(r'去年|此前|历史|last\s+year|previously', re.I).search(opening)
        and not source_denies_action(title, opening, r'发布|推出|announce|unveil|launch')
        and not _compiled_rule(r'取消|放弃|cancel|abandon', re.I).search(title + ' ' + opening))
    listed_report = bool(len(hardware_action_subjects(title)) >= 2 and _compiled_rule(
        r'\b(?:details?|specifications?)\b.{0,20}\b(?:leak\w*|reveal\w*)\b|多款.{0,20}细节', re.I).search(title))
    if evidence is not None and (listed_report or current_paragraph_report):
        # Captured product lists use local name declarations and carry the
        # owner into following descriptions. Never rewrite the source facts.
        groups: dict[str, list[str]] = {}
        aliases: dict[str, str] = {}
        current_owner = None
        partners: set[str] = set()
        items = []
        for unit in evidence.units:
            if unit.kind == 'li':
                items.append(unit.text)
            elif current_paragraph_report and unit.kind == 'p':
                for start, end in source_sentence_spans(unit.text):
                    items.extend(value.strip() for value in _compiled_rule(r'(?<=[；;])', 0).split(unit.text[start:end], 0) if value.strip())
        for value in items:
            historical_year = _compiled_rule(r'(?:自|在)?(20\d{2})年', 0).search(value)
            if (current_paragraph_report and historical_year and evidence.published_utc
                    and int(historical_year.group(1)) < int(evidence.published_utc[:4])):
                continue
            if current_paragraph_report and _compiled_rule(
                    r'^(?:如果|竞品|这意味着|通过让)|(?:去年|此前|上周五)|'
                    r'解决了.{0,20}弱点|通常享有|未能成为', re.I).search(value):
                continue
            declaration = _compiled_rule(r"(?:home\s+hub|家庭中枢|家居中枢).{0,65}?(?:named|called|命名为|定名)\s*[\"“‘']?([a-z][a-z0-9-]+)", re.I).search(value)
            reverse_declaration = _compiled_rule(r'名为\s*([a-z][a-z0-9-]+)\s*的.{0,20}(?:家居|家庭)中枢', re.I).search(value)
            if declaration or reverse_declaration:
                aliases[(declaration or reverse_declaration).group(1).lower()] = 'apple-home-hub'
            owned_value = _compiled_rule(r'^(?:unlike|in\s+contrast\s+to|compared\s+(?:with|to))\b[^,，]+[,，]\s*|^(?:与[^，]+不同|相比[^，]+)[，,]\s*', re.I).sub('', value, 1)
            named = {owner for alias, owner in aliases.items() if _compiled_rule(r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])', re.I).search(owned_value)}
            subjects = hardware_action_subjects(owned_value)
            primary = owned_multi_product_hardware_subject(owned_value)
            joint_development = bool(_compiled_rule(
                r'developed\s+in\s+partnership\s+with\s+apple|apple\s+and\s+[^.!?]{1,40}\s+co.developed|苹果与[^。]{1,25}合作开发|(?:苹果|该公司).{0,10}与[^。]{1,45}合作[^。]{0,40}(?:研发|开发|设计)', re.I).search(owned_value)
                and not source_denies_action(owned_value, '', r'(?:co.)?develop\w*|合作开发')
                and not _compiled_rule(r'\b(?:might|could|may)\s+(?:be\s+)?(?:co.)?develop|可能.{0,10}合作开发', re.I).search(owned_value))
            if joint_development:
                partner = _compiled_rule(r'与([^，。]{1,18}?)(?:展开|合作)', re.I).search(owned_value)
                if partner:
                    partners.add(partner.group(1).strip())
                    short = _compiled_rule(r'^[A-Za-z]+', 0).match(partner.group(1).strip())
                    if short: partners.add(short.group())
            local_partner = any(name in owned_value for name in partners)
            paragraph_accessory = bool(current_paragraph_report and (
                (local_partner and _compiled_rule(r'制造|产品支持|承担|财务|发货', re.I).search(owned_value))
                or (current_owner == 'apple-home-accessories' and _compiled_rule(r'称为|合作|配件.{0,30}(?:功能|性能)', re.I).search(owned_value))))
            accessory_continuation = bool(current_owner == 'apple-home-accessories'
                and _compiled_rule(r"^[A-Z][A-Za-z -]*['’]s\s+accessories", 0).search(owned_value))
            predicate = _compiled_rule(r'\b(?:will|is|has|supports?|features?)\b|将|会|支持|配备|搭载|有两个版本', re.I).search(owned_value)
            owned_alias = next((owner for alias, owner in aliases.items()
                if predicate and _compiled_rule(r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])', re.I).search(owned_value[:predicate.start()])), None)
            if joint_development or accessory_continuation or paragraph_accessory:
                owner = 'apple-home-accessories'
            elif len(subjects) >= 2 and _compiled_rule(r'\b(?:and|both)\b|和|与', re.I).search(owned_value) and _compiled_rule(r'launch|ship|上市|发货|交付', re.I).search(owned_value):
                owner = 'apple-home-delivery-batch'
            elif owned_alias:
                owner = owned_alias
            elif current_paragraph_report and _compiled_rule(r'^(?:虽然屏幕|另一款|台面式|壁挂式)', re.I).search(owned_value):
                owner = current_owner
            elif primary:
                owner = primary
            elif named and (not predicate or len(subjects) == 0):
                owner = next(iter(named))
            elif len(subjects) == 1:
                owner = next(iter(subjects))
            elif _compiled_rule(r'^(?:it|the\s+(?:device|model)|this|它|该设备|这款|台面式|壁挂式|一款经过)', re.I).search(owned_value):
                owner = current_owner
            else:
                owner = None
            if current_paragraph_report:
                concrete = _compiled_rule(r'配备|配有|搭载|内置|版本|配色|支持|触控|控制|测试|升级|交付|发货|推出|合作|研发|开发|称为|制造|负责|承担|名为|名称|设计', re.I).search(owned_value)
                if owner not in {'apple-home-hub','homepod','homepod-mini','apple-tv','apple-home-accessories','apple-home-delivery-batch'} or not concrete or source_denies_action(owned_value, '', r'发布|交付|研发|开发|合作'):
                    owner = None
            if owner:
                groups.setdefault(owner, []).append(value)
            if owner or not current_paragraph_report:
                current_owner = owner
        labels = {'apple-home-hub': 'Apple smart home hub device disclosure',
            'homepod': 'Apple HomePod mini device disclosure',
            'homepod-mini': 'Apple HomePod mini device disclosure',
            'apple-tv': 'Apple TV 4K hardware configuration disclosure',
            'apple-home-accessories': 'Apple smart home accessories partnership disclosure',
            'apple-home-delivery-batch': 'Apple TV and HomePod mini joint delivery schedule'}
        if current_paragraph_report:
            for owner in ('apple-tv', 'homepod'):
                own_text = ' '.join(groups.get(owner, ()))
                if owner == 'apple-tv':
                    model = _compiled_rule(r'apple\s*tv\s*(4k|hd)(?![a-z0-9])', re.I).search(own_text)
                    labels[owner] = 'Apple TV' + (' ' + model.group(1).upper() if model else '') + ' hardware configuration disclosure'
                if owner == 'homepod' and not _compiled_rule(r'homepod\s*mini', re.I).search(own_text):
                    labels[owner] = 'Apple HomePod device disclosure'
        if len(groups) >= 2:
            return [(labels.get(owner, 'Apple ' + owner.replace('-', ' ') + ' device disclosure'),
                     ' '.join(facts[:6]), facts[:fact_limit]) for owner, facts in groups.items()]

    umbrella_title = bool(
        _compiled_rule(r"\b(?:smart[- ]home\s+(?:products?|hardware|lineup|refresh)|"
            r"home\s+products?\s+nearly\s+ready)\b|"
            r"智能家居.{0,18}(?:多款|产品|新品|硬件|阵容|布局|进军)", 0).search(title_lower)
    )
    if not umbrella_title:
        return original
    content = " ".join([title, summary, *key_facts])
    lower = content.lower()
    tv_terms = (
        "apple tv",
        "homepod mini",
        "苹果电视",
        "homepod mini",
    )
    hub_terms = (
        "apple home hub",
        "smart home hub",
        "home hub",
        "家庭中枢",
        "智能家居中枢",
        "security camera",
        "home camera",
        "安防摄像头",
        "家用摄像头",
    )
    if score_terms(lower, tv_terms) <= 0 or score_terms(lower, hub_terms) <= 0:
        return original

    sentences = [
        clean_sentence(value)
        for value in [*key_facts, *_compiled_rule(r"(?<=[.!?。！？])\s*", 0).split(summary, 0)]
        if clean_sentence(value)
    ]

    def select(terms: tuple[str, ...]) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()
        for sentence in sentences:
            if score_terms(sentence.lower(), terms) > 0:
                add_unique_text(selected, seen, sentence)
        return selected[:fact_limit]

    tv_facts = select(tv_terms)
    hub_facts = select(hub_terms)
    if not tv_facts or not hub_facts:
        return original
    return [
        (
            "Apple TV and HomePod mini launch roadmap",
            " ".join(tv_facts[:5]),
            tv_facts,
        ),
        (
            "Apple home hub and smart-home accessories roadmap",
            " ".join(hub_facts[:5]),
            hub_facts,
        ),
    ]



def project_multi_family_iphone_report(
    title: str,
    summary: str,
    key_facts: list[str],
    *, fact_limit: int,
) -> list[tuple[str, str, list[str]]]:
    """Split a current multi-family iPhone report only on exclusive facts."""
    original = [(title, summary, key_facts)]
    title_lower = title.lower()
    if score_terms(title_lower, ["iphone", "苹果手机", "苹果新机"]) <= 0:
        return original
    title_subjects = iphone_report_subjects(title)
    combined = " ".join([title, summary, *key_facts])
    combined_subjects = iphone_report_subjects(combined)
    aggregate_report_terms = [
        "multiple",
        "several",
        "roadmap",
        "lineup",
        "product family",
        "models",
        "plans for",
        "多重",
        "多项",
        "多款",
        "多机型",
        "产品线",
        "阵容",
        "路线图",
        "规划",
    ]
    current_report = score_terms(
        title_lower,
        [
            "report",
            "reported",
            "reveal",
            "reveals",
            "leak",
            "leaked",
            "details",
            "曝光",
            "爆料",
            "细节",
            "进展",
        ],
    ) > 0
    shared_headline_action = bool(
        _compiled_rule(r"\b(?:prices?|pricing|costs?|colors?|colou?rs?|finishes?|production|"
            r"shipments?|orders?|preorders?|pre-orders?|availability|sales?|benchmarks?|measurements?)\b|"
            r"(?:价格|售价|成本|配色|颜色|量产|生产|出货|订单|预购|供货|开售|销量|跑分|实测)", re.I).search(title_lower)
    )
    # Multiple model names do not make a multi-action report when the headline
    # owns one shared price, finish, production, availability, or sales action.
    # A generic current-report headline naming several product families can be
    # projected when its facts give each family an exclusive concrete claim.
    multi_subject_headline = bool(
        len(combined_subjects) >= 2
        and (
            score_terms(title_lower, aggregate_report_terms) > 0
            or (
                len(title_subjects) >= 2
                and current_report
                and not shared_headline_action
            )
        )
    )
    if not multi_subject_headline or not current_report:
        return original

    sentences: list[str] = []
    seen: set[str] = set()
    for value in [summary, *key_facts]:
        for start, end in source_sentence_spans(value):
            add_unique_text(sentences, seen, clean_sentence(value[start:end]), min_chars=12)
    exclusive: dict[str, list[str]] = {}
    for sentence in sentences:
        subjects = iphone_report_subjects(sentence)
        if len(subjects) == 1:
            # A different model's completed launch is context for a current
            # design report, not a second roadmap action to project.
            if _compiled_rule(r"\b(?:last\s+(?:week|month|year)|previously|earlier)\b|上周|上月|此前", re.I).search(sentence) and _compiled_rule(r"\b(?:arrived|launched|released|came\s+out)\b|已发布|已上市", re.I).search(sentence):
                continue
            exclusive.setdefault(next(iter(subjects)), []).append(sentence)
    if len(exclusive) < 2:
        return original

    labels = {
        "foldable-iphone": "Apple foldable iPhone roadmap update",
        "anniversary-iphone": "Apple anniversary iPhone design update",
    }
    variants: list[tuple[str, str, list[str]]] = []
    for subject, facts in exclusive.items():
        title_label = labels.get(subject, f"Apple {subject.replace('-', ' ').title()} hardware roadmap update")
        variants.append((title_label, " ".join(facts[:6]), facts[:fact_limit]))
    return variants



from .event_identity import (MULTI_PRODUCT_HARDWARE_SUBJECTS, multi_product_hardware_subjects, hardware_action_subjects,
    owned_multi_product_hardware_subject, heading_owned_multi_product_hardware_subject,
    foldable_iphone_generation_subject, apple_silicon_generation_keys)
from .event_reconciler import hardware_roadmap_primary_claim, is_multi_year_apple_product_wave

def project_hardware_roadmap(
    title: str,
    summary: str,
    key_facts: list[str],
    *, identity: EventIdentity, single_source_disclosure: bool, fact_limit: int,
    evidence: ArticleEvidence | None = None,
) -> list[tuple[str, str, list[str]]]:
    """Project an explicit multi-product roadmap onto its product-level actions."""
    original = [(title, summary, key_facts)]
    title_lower = title.lower()
    device = source_device_operation_frame(title, summary, tuple(key_facts))
    if single_source_disclosure or (device and device.action == "device-announcement"):
        return original
    if _compiled_rule(r"\b(?:unidentified|unresolved|unknown)\b.{0,36}"
        r"\b(?:device|product|hardware)\s+identifiers?\b|"
        r"(?:未识别|未确认|无法确认|尚未确认).{0,18}(?:设备|产品|硬件).{0,12}(?:标识|型号)|"
        r"(?:设备|产品|硬件).{0,12}(?:标识|型号).{0,18}(?:未识别|未确认|无法确认|尚未确认)", re.I).search(title_lower):
        return original
    title_subjects = hardware_action_subjects(title)
    values: list[str] = []
    seen: set[str] = set()
    value_owner_hints: dict[str, str] = {}
    value_iphone_owner_hints: dict[str, str] = {}
    title_owned_clause_subjects: set[str] = set()
    if len(title_subjects) >= 2:
        for title_clause in _compiled_rule(r"[,，;；]", 0).split(title, 0):
            cleaned_clause = clean_sentence(title_clause).strip(" ,，;；:-")
            clause_subjects = hardware_action_subjects(cleaned_clause)
            if len(clause_subjects) != 1:
                continue
            if not _compiled_rule(r"\b(?:will|expected|expects?|launch(?:es|ed|ing)?|release(?:s|d|ing)?|"
                r"ship(?:s|ped|ping)?|arrive(?:s|d|ing)?|predicted|forecast|coming)\b|"
                r"(?:预计|预期|将于|将在|发布|推出|上市|亮相|登场|面世)", re.I).search(cleaned_clause):
                continue
            add_unique_text(values, seen, cleaned_clause, min_chars=12)
            title_owned_clause_subjects.update(clause_subjects)
    for raw_value in [summary, *key_facts]:
        current_owner: str | None = None
        current_iphone_owner: str | None = None
        for sentence in _compiled_rule(r"(?<=[。！？])\s*|(?<=[.!?])\s+", 0).split(raw_value, 0):
            sentence_owner = heading_owned_multi_product_hardware_subject(sentence)
            if sentence_owner is not None:
                current_owner = sentence_owner
                heading = _compiled_rule(r"^([^：:\n]{2,80})[：:]", 0).match(clean_sentence(sentence))
                heading_iphone_subjects = (
                    iphone_report_subjects(heading.group(1)) if heading else set()
                )
                current_iphone_owner = (
                    next(iter(heading_iphone_subjects))
                    if sentence_owner == "iphone" and len(heading_iphone_subjects) == 1
                    else None
                )
            # A report often states one owned product action before
            # "alongside" and then lists the rest of an event lineup. Split
            # that coordination boundary so the owned action can be projected;
            # the multi-product lineup clause remains background because it
            # still contains several subjects and no independent predicate.
            for value in _compiled_rule(r"\s+\b(?:alongside|together with)\b\s+|"
                r"(?:并)?与(?=[^。！？]{0,80}(?:一同|共同|同步))", re.I).split(sentence, 1):
                cleaned_value = clean_sentence(value)
                add_unique_text(values, seen, cleaned_value, min_chars=12)
                if current_owner is not None and len(cleaned_value) >= 12:
                    owner_key = _compiled_rule(r"[^0-9a-z\u4e00-\u9fff]+", 0).sub(" ", clean_fact_text(cleaned_value).lower(), 0).strip()[:180]
                    if owner_key:
                        value_owner_hints[owner_key] = current_owner
                        if current_iphone_owner is not None:
                            value_iphone_owner_hints[owner_key] = current_iphone_owner
    # Product headings and product-led paragraphs own their following local
    # descriptions. Keep the original text for exact source-span accounting;
    # do not synthesize a product name into an otherwise unowned sentence.
    if evidence is not None and len(title_subjects) >= 2:
        section_owner = None
        for unit in evidence.units:
            if unit.kind in {"h2", "h3"}:
                heading_subjects = hardware_action_subjects(unit.text)
                section_owner = next(iter(heading_subjects)) if len(heading_subjects) == 1 else None
                continue
            if unit.kind != "p" or unit.container_id == "caption":
                continue
            sentences = _compiled_rule(r"(?<=[。！？])\s*|(?<=[.!?])\s+", 0).split(unit.text, 0)
            paragraph_owner = owned_multi_product_hardware_subject(sentences[0]) if sentences else None
            if paragraph_owner is not None and paragraph_owner not in title_subjects:
                section_owner = None
                continue
            owner = paragraph_owner or section_owner
            if owner not in title_subjects:
                continue
            for sentence in sentences:
                cleaned = clean_sentence(sentence)
                add_unique_text(values, seen, cleaned, min_chars=12)
                key = _compiled_rule(r"[^0-9a-z\u4e00-\u9fff]+", 0).sub(" ", clean_fact_text(cleaned).lower(), 0).strip()[:180]
                if key:
                    value_owner_hints[key] = owner
    grouped: dict[str, list[str]] = {}
    for value in values:
        owner_key = _compiled_rule(r"[^0-9a-z\u4e00-\u9fff]+", 0).sub(" ", clean_fact_text(value).lower(), 0).strip()[:180]
        subject = (
            heading_owned_multi_product_hardware_subject(value)
            or value_owner_hints.get(owner_key)
            or owned_multi_product_hardware_subject(value)
        )
        if subject is not None:
            grouped.setdefault(subject, []).append(value)
    iphone_claim_groups: dict[str, dict[str, list[str]]] = {}
    for subject, facts in grouped.items():
        if subject != "iphone":
            continue
        for fact in facts:
            owner_key = _compiled_rule(r"[^0-9a-z\u4e00-\u9fff]+", 0).sub(" ", clean_fact_text(fact).lower(), 0).strip()[:180]
            iphone_subjects = iphone_report_subjects(fact)
            if not iphone_subjects and owner_key in value_iphone_owner_hints:
                iphone_subjects = {value_iphone_owner_hints[owner_key]}
            if len(iphone_subjects) != 1:
                continue
            iphone_subject = next(iter(iphone_subjects))
            if iphone_subject == "foldable-iphone":
                iphone_subject = foldable_iphone_generation_subject(fact)
            iphone_claim_groups.setdefault(subject, {}).setdefault(
                iphone_subject,
                [],
            ).append(fact)
    headline_roadmap_claim = hardware_roadmap_primary_claim(title, summary)
    headline_roadmap_action = (
        headline_roadmap_claim[1] if headline_roadmap_claim is not None else ""
    )
    roadmap_claim_groups: dict[str, dict[tuple[str, str, str], list[str]]] = {}
    for fact in values:
        fact_lower = fact.lower()
        if _compiled_rule(r"^(?:with\s+)?(?:both|these|those|the\s+two)\b.{0,48}"
            r"\b(?:products?|devices?|models?|programs?|product\s+lines?)\b|"
            r"^(?:上述|这两|两者|这些|该批).{0,32}(?:产品|设备|机型|项目|产品线)", re.I).search(fact_lower):
            # A collective consequence restates already enumerated
            # programs; it is not a third project to synthesize.
            continue
        if _compiled_rule(r"\bfold(?:able|ing)\b.{0,100}\band\s+(?:a|an|another|a\s+separate)\b"
            r".{0,100}\boled\b|"
            r"(?:折叠|全屏).{0,80}(?:以及|和|与|另(?:一|外)).{0,80}oled", re.I).search(fact_lower):
            # A sentence that summarizes two explicitly coordinated
            # programs belongs to neither projected child; the following
            # product-owned facts carry the actionable details.
            continue
        claim = hardware_roadmap_primary_claim(fact)
        if claim is None:
            continue
        if headline_roadmap_action and claim[1] != headline_roadmap_action:
            # A counted headline owns one action. Other roadmap details in
            # the article are context and must not become synthetic events.
            continue
        roadmap_claim_groups.setdefault(claim[0], {}).setdefault(claim, []).append(fact)
    has_distinct_roadmap_claims = sum(
        len(claims) for claims in roadmap_claim_groups.values()
    ) >= 2
    explicit_same_family_programs = bool(
        len(title_subjects) == 1
        and _compiled_rule(r"\b(?:two|three|four|five|six|several|multiple)\b"
            r".{0,45}\b(?:new\s+)?(?:models?|devices?|products?|"
            r"macbooks?|iphones?|ipads?|imacs?|homepods?|airpods)\b|"
            r"\b\d{1,2}\s+(?:new\s+)?(?:models?|devices?|products?|"
            r"macbooks?|iphones?|ipads?|imacs?|homepods?|airpods)\b|"
            r"(?:两|三|四|五|六|多|\d+)\s*(?:款|个|项).{0,24}"
            r"(?:机型|设备|产品|项目|macbook|iphone|ipad|imac|homepod|airpods)", re.I).search(title_lower)
    )
    opening_lead = _compiled_rule(r"(?<=[。！？])\s*|(?<=[.!?])\s+", 0).split(clean_sentence(summary), 1)[0][:700]
    coordinated_opening_programs = bool(
        len(title_subjects) == 1
        and has_distinct_roadmap_claims
        and headline_roadmap_action
        and _compiled_rule(r"\b(?:and|as\s+well\s+as|alongside)\b|(?:和|及|以及|同时)", re.I).search(opening_lead)
        and {
            qualifier
            for claims in roadmap_claim_groups.values()
            for (_product, action, qualifier) in claims
            if action == headline_roadmap_action
            and (
                qualifier == "foldable-form-factor"
                and _compiled_rule(r"\b(?:fold(?:able|ing)|all[- ]screen)\b|(?:折叠|全屏)", re.I).search(opening_lead)
                or qualifier == "oled-form-factor"
                and _compiled_rule(r"\boled\b", re.I).search(opening_lead)
                or qualifier == "product-program"
            )
        }
        >= {
            qualifier
            for claims in roadmap_claim_groups.values()
            for (_product, action, qualifier) in claims
            if action == headline_roadmap_action
        }
    )
    explicit_same_family_programs = (
        explicit_same_family_programs or coordinated_opening_programs
    )
    structured_report_scope = f"{title} {opening_lead}"
    structured_title_catalog_scope = bool(
        len(title_subjects) >= 2
        or _compiled_rule(r"\b(?:two|three|four|five|six|several|multiple|more\s+than\s+\d+|\d{1,2})\b"
            r".{0,45}\b(?:unreleased\s+)?(?:apple\s+)?(?:products?|devices?|hardware)\b|"
            r"\b(?:apple\s+)?product\s+(?:identifier|codename|reference)\s+(?:leak|list|catalog)\b|"
            r"(?:两|三|四|五|六|多|\d+)\s*(?:款|个|项).{0,24}"
            r"(?:未发布|即将推出|新款)?(?:苹果)?(?:产品|设备|硬件|新品)|"
            r"(?:大量|一批|多款).{0,24}(?:苹果)?(?:未发布)?(?:产品|设备|硬件|新品)"
            r".{0,20}(?:代号|标识符?|清单)", re.I).search(title_lower)
    )
    structured_multi_product_report = bool(
        len(grouped) >= 2
        and structured_title_catalog_scope
        and _compiled_rule(r"\b(?:code|codes|identifier|identifiers|codename|codenames|reference|references)\b|"
            r"(?:代码|标识符|产品标识|代号|资源清单)", re.I).search(structured_report_scope)
        and _compiled_rule(r"\b(?:unreleased|upcoming|new)\b.{0,36}\b(?:apple\s+)?(?:products?|devices?|hardware)\b|"
            r"\b(?:products?|devices?|hardware)\b.{0,36}\b(?:code|identifier|codename|reference)\b|"
            r"\b(?:apple\s+)?product\s+(?:identifier|codename|reference)\s+(?:leak|list|catalog)\b|"
            r"(?:未发布|即将推出|多款|新款).{0,24}(?:苹果)?(?:产品|设备|硬件|新品)|"
            r"(?:产品|设备|硬件|新品).{0,24}(?:代码|标识符|产品标识|代号|资源清单)", re.I).search(structured_report_scope)
    )
    broad_family_roadmap = bool(
        grouped
        and _compiled_rule(r"\b(?:apple(?:'s)?\s+)?(?:mac|iphone|ipad|airpods|apple\s+watch|home)\s+"
            r"(?:roadmap|lineup|product\s+line|pipeline)\b|"
            r"(?:苹果)?(?:mac|iphone|ipad|airpods|apple\s*watch|家庭硬件)"
            r"(?:路线图|产品线|阵容|规划)", re.I).search(title_lower)
    )
    explicit_multi_option_report = bool(
        len(grouped) >= 2
        and _compiled_rule(r"\b(?:two|three|four|five|six|several|multiple|\d{1,2})\b"
            r".{0,45}\b(?:options?|models?)\b|"
            r"(?:两|三|四|五|六|多|(?<!\d)(?!(?:19|20)\d{2})\d{1,2})\s*(?:款|种)"
            r"(?![^。！？]{0,24}(?:无法|不能|不可|不支持)升级).{0,24}(?:选择|机型)", re.I).search(title_lower)
    )
    explicit_multi_product = bool(
        _compiled_rule(r"\b(?:two|three|four|five|six|several|multiple|(?!(?:19|20)\d{2}\b)\d{1,2})\b"
            r".{0,45}\b(?:new\s+)?(?:apple\s+)?(?:hardware\s+)?products?\b|"
            r"(?:多达|至少|共计|共有|将有)?\s*(?:两|三|四|五|六|(?<!\d)(?!(?:19|20)\d{2})\d{1,2})\s*款"
            r".{0,28}(?:苹果)?(?:新品|产品|设备)", 0).search(title_lower)
        or (
            len(title_subjects) >= 2
            and score_terms(
                title_lower,
                [
                    "will launch",
                    "plans to launch",
                    "to launch",
                    "will release",
                    "plans to release",
                    "expected",
                    "predicted",
                    "forecast",
                    "coming",
                    "pipeline",
                    "in the pipeline",
                    "roadmap",
                    "rumored",
                    "将推出",
                    "将于",
                    "预测",
                    "即将推出",
                    "即将发布",
                    "亮相",
                    "登场",
                    "面世",
                    "路线图",
                    "传闻",
                ],
            )
            > 0
        )
        or (
            len(title_subjects) >= 2
            and _compiled_rule(r"\b(?:days? away|within (?:the )?(?:next )?few days|coming days|"
                r"launch(?:es|ing)?|release(?:s|d|ing)?|scheduled|in (?:september|october))\b|"
                r"(?:未来几天|数日)(?:之)?内.{0,10}(?:发布|推出|亮相)|"
                r"(?:发布|推出|亮相|定档).{0,12}(?:\d{1,2}\s*月|年内)", re.I).search(title_lower)
        )
        or len(title_owned_clause_subjects) >= 2
        or structured_multi_product_report
        or broad_family_roadmap
        or explicit_multi_option_report
        or (explicit_same_family_programs and has_distinct_roadmap_claims)
        or (
            (
                len(grouped) >= 2
                or any(len(groups) >= 2 for groups in iphone_claim_groups.values())
            )
            and is_multi_year_apple_product_wave(title, summary)
        )
    )
    if not explicit_multi_product:
        return original
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return original

    generation_groups: dict[str, dict[str, list[str]]] = {}
    for subject, facts in grouped.items():
        for fact in facts:
            generations = apple_silicon_generation_keys(fact)
            if len(generations) == 1:
                generation_groups.setdefault(subject, {}).setdefault(
                    next(iter(generations)), []
                ).append(fact)
    has_distinct_generation_actions = any(
        len(groups) >= 2 for groups in generation_groups.values()
    ) or any(
        len(groups) >= 2 for groups in iphone_claim_groups.values()
    )
    if (
        len(grouped) < 2
        and not has_distinct_generation_actions
        and not (explicit_same_family_programs and has_distinct_roadmap_claims)
    ):
        return original

    explicit_launch_report = bool(
        _compiled_rule(r"\b(?:two|three|four|five|six|several|multiple|(?!(?:19|20)\d{2}\b)\d{1,2})\b"
            r".{0,45}\b(?:new\s+)?(?:apple\s+)?(?:hardware\s+)?products?\b", 0).search(title_lower)
        and _compiled_rule(r"\b(?:rumored|reported|expected|will|plans?|set)\b.{0,45}"
            r"\b(?:launch|release|ship|arrive|debut)\b", 0).search(title_lower)
    )

    labels = {subject: label for subject, label, _terms in MULTI_PRODUCT_HARDWARE_SUBJECTS}
    variants: list[tuple[str, str, list[str]]] = []
    if explicit_same_family_programs and has_distinct_roadmap_claims:
        canonical_labels = {
            "foldable-apple-computer": "foldable Mac/iPad",
            "macbook": "MacBook",
        }
        for product, claims in sorted(roadmap_claim_groups.items()):
            for (_product, action, qualifier), claim_facts in sorted(claims.items()):
                scoped_facts: list[str] = []
                scoped_seen: set[str] = set()
                for fact in claim_facts:
                    add_unique_text(scoped_facts, scoped_seen, fact)
                product_label = canonical_labels.get(product, product.replace("-", " ").title())
                if action == "project-cancellation":
                    form = {
                        "foldable-form-factor": "foldable ",
                        "oled-form-factor": "OLED ",
                    }.get(qualifier, "")
                    if product == "foldable-apple-computer":
                        form = ""
                    variant_title = f"Apple cancels {form}{product_label} project"
                else:
                    variant_title = f"Apple {product_label} {action.replace('-', ' ')}"
                variants.append(
                    (
                        variant_title,
                        " ".join(scoped_facts[:6]),
                        scoped_facts[:fact_limit],
                    )
                )
        return variants or original
    for subject, facts in grouped.items():
        subject_iphone_claim_groups = iphone_claim_groups.get(subject, {})
        if (
            len(subject_iphone_claim_groups) >= 2
            and (
                broad_family_roadmap
                or explicit_launch_report
                or is_multi_year_apple_product_wave(title, summary)
            )
        ):
            iphone_labels = {
                "anniversary-iphone": "Apple anniversary iPhone design update",
                "foldable-iphone": "Apple iPhone Ultra roadmap update",
                "foldable-iphone-g2": "Apple second-generation foldable iPhone roadmap update",
                "foldable-iphone-g3": "Apple third-generation foldable iPhone roadmap update",
            }
            for iphone_subject, iphone_facts in sorted(
                subject_iphone_claim_groups.items()
            ):
                scoped_facts: list[str] = []
                scoped_seen: set[str] = set()
                for fact in iphone_facts:
                    add_unique_text(
                        scoped_facts,
                        scoped_seen,
                        fact,
                        min_chars=12,
                    )
                variant_title = iphone_labels.get(
                    iphone_subject,
                    (
                        f"Apple iPhone {iphone_subject.removeprefix('iphone-')} roadmap update"
                        if iphone_subject.startswith("iphone-")
                        else f"Apple {iphone_subject.replace('-', ' ').title()} roadmap update"
                    ),
                )
                variants.append(
                    (
                        variant_title,
                        " ".join(scoped_facts[:6]),
                        scoped_facts[:fact_limit],
                    )
                )
            continue
        subject_generation_groups = generation_groups.get(subject, {})
        if len(subject_generation_groups) >= 2:
            for generation, generation_facts in sorted(subject_generation_groups.items()):
                scoped_facts: list[str] = []
                scoped_seen: set[str] = set()
                for fact in generation_facts:
                    add_unique_text(scoped_facts, scoped_seen, fact)
                variants.append(
                    (
                        f"Apple {labels[subject]} {generation.upper()} roadmap update",
                        " ".join(scoped_facts[:6]),
                        scoped_facts[:fact_limit],
                    )
                )
            continue
        scoped_facts: list[str] = []
        scoped_seen: set[str] = set()
        for fact in facts:
            add_unique_text(scoped_facts, scoped_seen, fact, min_chars=12)
        # Short, identifier-dense facts can be below the normal summary-text
        # length threshold. They still carry the strongest evidence for a
        # structured child action, so use the raw group for identity checks.
        evidence_facts = scoped_facts or facts
        scoped_text = " ".join(evidence_facts).lower()
        deictic_co_launch = bool(
            _compiled_rule(r"\b(?:during|at)\s+(?:the\s+)?event\b|\b(?:alongside|at the same time)\b|"
                r"(?:届时|同场|同步).{0,24}(?:发布|推出|亮相|上市|登场)", re.I).search(scoped_text)
        )
        standalone_launch_window = bool(
            _compiled_rule(r"\b(?:within (?:the )?(?:next )?few days|coming days|next month|"
                r"january|february|march|april|may|june|july|august|september|"
                r"october|november|december|20\d{2}\s*q[1-4])\b|"
                r"(?:未来几天|数日内|下月|明年|20\d{2}\s*年|\d{1,2}\s*月)", re.I).search(scoped_text)
        )
        # A sentence that only says another product will launch "then" is
        # context for the parent report, not an independently owned roadmap
        # claim. Keep it when the sentence supplies its own concrete window.
        if deictic_co_launch and not standalone_launch_window:
            continue
        known_mapping = score_terms(
            scoped_text,
            [
                "known and sold",
                "already sold",
                "currently sold",
                "confirmed by apple",
                "confirmed mainland",
                "used for a known",
                "belongs to the",
                "已知产品",
                "已经上市",
                "已上市",
                "在售产品",
                "苹果已确认",
                "现有产品",
            ],
        ) > 0
        unreleased_mapping = score_terms(
            scoped_text,
            [
                "unreleased",
                "upcoming",
                "new model",
                "unknown model",
                "not yet released",
                "未发布",
                "即将推出",
                "新款",
                "未知型号",
                "尚未上市",
                "代码线索",
            ],
        ) > 0
        if known_mapping and not unreleased_mapping:
            continue
        concrete_subject_evidence = bool(
            unreleased_mapping
            or _compiled_rule(r"\b(?:code|identifier|codename|reference|model number|project id|"
                r"prototype|testing|in development|preparing|developing|in the pipeline|canceled|cancelled|delayed|"
                r"production|resource list|will launch|will release|will ship|"
                r"goal of releasing|forecast to bring out|predicted for|"
                r"will be launched|will be released|will be shipped|"
                r"(?:will|is expected to|are expected to|is planned to|are planned to)\s+"
                r"(?:use|adopt|feature|include|offer|keep|retain|move|add)|"
                r"keeps?|retains?|moves?|adds?|features?|uses?|adopts?|includes?|offers?|"
                r"starts? production|enters? production|scheduled to launch|"
                r"expected to launch|expects?\b.{0,64}\bto\s+(?:launch|release|ship)|"
                r"reportedly|according to)\b|"
                r"\b[a-z][a-z0-9]{0,20}\d{2,}(?:,\d+)?\b|"
                r"(?:代码|标识符|产品标识|代号|型号|项目编号|原型机|测试中|开发中|筹备(?:中)?|准备推出|"
                r"取消|延期|量产|资源清单|将推出|将发布|将出货|计划发布|预计发布|"
                r"有望.{0,18}(?:推出|发布|亮相)|(?:将|预计|计划)(?:采用|搭载|配备|保留|改用|换用|新增)|"
                r"(?:采用|搭载|配备|保留|改用|换用|新增|升级|更新|推出|发布|亮相)|消息称|据称|据报道)", re.I).search(scoped_text)
        )
        first_person_inference = bool(
            _compiled_rule(r"\b(?:i\s+(?:think|suspect|imagine|hope|expect|am|have|use)|"
                r"i['’](?:m|ve)|my\s+(?:main|favorite))\b|"
                r"(?:我(?:认为|怀疑|猜测|希望|期待|一直|正在|使用)|我最喜欢)", re.I).search(scoped_text)
        )
        if (not concrete_subject_evidence and not explicit_launch_report) or first_person_inference:
            continue
        specific_label = labels[subject]
        for pattern, generic_pattern, label in (
            (
                r"\biphone\s+ultra\b|\bfoldable\s+iphone\b|折叠(?:屏)?\s*iphone",
                r"\biphone\b|苹果(?:手机|新机)",
                "iPhone Ultra",
            ),
            (r"\bairpods\s+ultra\b", r"\bairpods\b|苹果耳机", "AirPods Ultra"),
            (r"\bmacbook\s+ultra\b", r"\bmacbook\b|苹果笔记本", "MacBook Ultra"),
        ):
            if not re.search(pattern, scoped_text):
                continue
            remaining_scope = re.sub(pattern, " ", scoped_text, flags=re.I)
            if not re.search(generic_pattern, remaining_scope, re.I):
                specific_label = label
                break
        configuration_report = bool(subject in {"homepod", "apple-tv"}
            and _compiled_rule(r"新款|新一代|此次更新", re.I).search(scoped_text)
            and _compiled_rule(r"(?:将|将在).{0,45}(?:处理性能|处理器|内部硬件)", re.I).search(scoped_text)
            and _compiled_rule(r"据称|消息显示|消息人士|透露", re.I).search(scoped_text)
            and not _compiled_rule(r"去年|此前|旧款|取消|否认|预购|交付|发货|价格|售价", re.I).search(scoped_text))
        if subject == "homepod" and _compiled_rule(r"(?<![a-z0-9])homepod\s*mini(?![a-z])", re.I).search(scoped_text):
            specific_label = "HomePod mini"
            devices = disclosed_device_subjects(evidence.raw_lead if evidence else summary)
            if devices.get("homepod-mini"):
                specific_label += " " + devices["homepod-mini"]
        variant_title = f"Apple {specific_label} " + ("hardware configuration disclosure" if configuration_report else "roadmap update")
        variants.append(
            (variant_title, " ".join(evidence_facts[:6]), evidence_facts[:fact_limit])
        )
    return variants or original



def _source_release_signatures(identity: EventIdentity) -> set[tuple[str, str, str]]:
    waves = [match.groups() for component in identity.components
             if (match := _compiled_rule(r"os-wave:([^:]+):([^:]+)", 0).fullmatch(component))]
    platforms = [match.groups() for component in identity.components
                 if (match := _compiled_rule(r"os-wave-platform:([^:]+):([^:]+)", 0).fullmatch(component))]
    return {(platform, version, stage) for version, stage in waves
            for platform, platform_stage in platforms if stage == platform_stage}


def project_current_release_inventory(title: str, summary: str, evidence: ArticleEvidence | None,
                                      fact_limit: int) -> list[tuple[str, str, list[str]]]:
    """Bind each platform/version to its own row under a current release list.

    An OS name in a compatibility list is insufficient. Both the page opening
    and the immediate list introduction must assert a present public release.
    Unassigned commentary remains available through source dispositions.
    """
    if evidence is None or not _compiled_rule(r"\b(?:updates?|releases?)\b|更新|发布", re.I).search(title):
        return []
    if _compiled_rule(r"\b(?:beta|rc|history|recap|expected|upcoming)\b|测试版|候选版|回顾|预计", re.I).search(title):
        return []
    opening = evidence.raw_lead or summary[:500]
    if (not _compiled_rule(r"\bapple(?:'s|’s)?\b|苹果", re.I).search(opening)
            or not _compiled_rule(r"\b(?:have\s+arrived|released|now\s+here|now\s+available)\b|已发布|正式发布|现已推送", re.I).search(opening)
            or _compiled_rule(r"\b(?:last\s+year|previously|not\s+released|have\s+not)\b|去年|此前|尚未发布", re.I).search(opening)):
        return []
    rows = {}
    active = False
    for unit in evidence.units:
        if unit.kind != "li":
            active = bool(_compiled_rule(r"\b(?:new\s+updates\s+are|apple\s+(?:also\s+)?released)\b|(?:本次|新发布).{0,12}更新.{0,10}(?:如下|包括)", re.I).search(unit.text)
                and not _compiled_rule(r"\b(?:previously|last\s+year|not|never|will)\b|去年|此前|尚未|将会", re.I).search(unit.text))
            continue
        match = _compiled_rule(r"\s*(iOS|iPadOS|macOS|watchOS|tvOS|visionOS)\s+(\d+(?:\.\d+){1,2})\s*[,，]\s*(?:build|构建号)\s+([0-9]+[a-z][0-9]+[a-z]?)\.?\s*", re.I).fullmatch(unit.text)
        if active and match:
            platform, version, _build = match.groups()
            rows.setdefault((platform, version), []).append(unit.text)
    if len(rows) < 2:
        return []
    return [(f"{platform} {version} update released", "Apple released " + " ".join(facts), facts[:fact_limit])
            for (platform, version), facts in rows.items()]


_OS_VERSION = _compiled_rule(r"\b(ios|ipados|macos|watchos|tvos|visionos)\s+(?:[a-z][a-z-]*\s+){0,2}(\d+(?:\.\d+){1,2})\b", re.I)


def _headline_released_versions(title: str) -> list[tuple[str, str]]:
    """Only the coordinated objects of 'Apple releases', never a later comparator."""
    action = _compiled_rule(r"^(?:apple\s+(?:releases|released)|苹果(?:发布|推送))\s*", re.I).match(title)
    if not action or _compiled_rule(r"\b(?:beta|rc|candidates?|will|expected)\b|测试|候选|预计", re.I).search(title):
        return []
    position, versions = action.end(), []
    while match := _OS_VERSION.match(title, position):
        versions.append(match.groups())
        separator = _compiled_rule(r"\s*(?:,\s*(?:and\s+)?|and\s+|、|和|与)\s*", re.I).match(title[match.end():])
        if not separator:
            break
        position = match.end() + separator.end()
    return list(dict.fromkeys(versions))


def _scoped_release_facts(versions: Sequence[tuple[str, str]], evidence: ArticleEvidence | None,
                          facts: Sequence[tuple[str, EventIdentity]]) -> dict[tuple[str, str], list[str]]:
    """Resolve explicit versions and locally introduced security-detail blocks."""
    labels = {(platform.lower(), version): (platform, version) for platform, version in versions}
    assigned = {label: [] for label in versions}
    passages = [(u.kind, u.text) for u in evidence.units] if evidence else [("p", text) for text, _ in facts]
    security_owners: set[tuple[str, str]] = set()
    for kind, passage in passages:
        # Contrast clauses can explicitly deny a CVE for one version and
        # introduce fixes for others. Keep each exact substring with its owner.
        for text in _compiled_rule(r"(?=\bbut\s+says\b)|(?=但(?:表示|称))", re.I).split(passage, 0):
            mentioned = {(platform.lower(), version) for platform, version in _OS_VERSION.findall(text)}
            owners = mentioned & labels.keys()
            if owners:
                security_owners = set()
                if len(mentioned) == 1 or _compiled_rule(r"\b(?:released|rolling\s+out|fix(?:es)?|address(?:es)?)\b|发布|修复", re.I).search(text):
                    for owner in owners:
                        if text not in assigned[labels[owner]]:
                            assigned[labels[owner]].append(text)
                if text.rstrip().endswith((":", "：")) and _compiled_rule(r"fix|address|修复", re.I).search(text):
                    security_owners = owners
            elif security_owners:
                if kind in {"h3", "h4"} or _compiled_rule(r"(?:Available for|Impact|Description|CVE-\d{4}-|适用|影响|描述)\b", re.I).match(text):
                    for owner in security_owners:
                        assigned[labels[owner]].append(text)
                else:
                    security_owners = set()
    return assigned


def project_os_release_variants(title: str, summary: str, key_facts: list[str], *,
        clauses: Sequence[tuple[str, EventIdentity]], facts: Iterable[tuple[str, EventIdentity]],
        fact_limit: int, evidence: ArticleEvidence | None = None) -> list[tuple[str, str, list[str]]]:
    """Release facts inherit their own platform, version and stage together."""
    title_versions = _headline_released_versions(title)
    if len(title_versions) > 1:
        scoped = _scoped_release_facts(title_versions, evidence, tuple(facts) if evidence is None else ())
        return [(f"{platform} {version} released", f"Apple released {platform} {version}. " + " ".join(scoped[(platform, version)]),
                 scoped[(platform, version)][:fact_limit]) for platform, version in title_versions]
    releases = [(clause, _source_release_signatures(identity)) for clause, identity in clauses]
    releases = [(clause, signatures) for clause, signatures in releases if signatures]
    if len(releases) < 2 or len({(version, stage) for _, signatures in releases for _, version, stage in signatures}) < 2:
        return [(title, summary, key_facts)]
    facts = tuple(facts)
    variants = []
    for clause, signatures in releases:
        scoped = [text for text, identity in facts if _source_release_signatures(identity) & signatures]
        variants.append((clause, " ".join(scoped) or clause, scoped[:fact_limit]))
    return variants


def _project_device_finance_claims(title: str, summary: str, key_facts: list[str], *,
                                  identity: EventIdentity, fact_limit: int) -> list[tuple[str, str, list[str]]]:
    compound_components = {
        "apple-device-leasing-program",
        "financed-device-restriction",
    }
    if not compound_components <= set(identity.title_components):
        return [(title, summary, key_facts)]

    program_terms = (
        "apple upgrade",
        "iphone upgrade program",
        "hardware subscription",
        "leasing program",
        "klarna",
        "lease term",
        "24-month",
        "36-month",
        "early upgrade",
        "buy out",
        "月租",
        "租赁计划",
        "租期",
        "24 个月",
        "36 个月",
        "提前升级",
        "买断",
    )
    restriction_terms = (
        "missed payment",
        "miss a payment",
        "miss payments",
        "unpaid",
        "overdue",
        "restricted mode",
        "partner finance lock",
        "system apps",
        "prevent erasure",
        "prevent resale",
        "欠款",
        "欠费",
        "受限模式",
        "白名单",
        "系统 app",
        "系统应用",
        "防止抹除",
        "防止拆",
        "转卖",
        "停用",
    )

    clauses = [clean_sentence(value) for value in _compiled_rule(r"[,，:：;；]", 0).split(title, 0) if clean_sentence(value)]

    def focused_title(terms: tuple[str, ...]) -> str:
        return next((clause for clause in clauses if score_terms(clause.lower(), terms) > 0), "")

    def focused_content(terms: tuple[str, ...], fallback_title: str) -> tuple[str, list[str]]:
        values: list[str] = []
        seen: set[str] = set()
        for value in [*key_facts, *_compiled_rule(r"(?<=[.!?。！？])\s*", 0).split(summary, 0)]:
            cleaned = clean_sentence(value)
            if cleaned and score_terms(cleaned.lower(), terms) > 0:
                add_unique_text(values, seen, cleaned)
        if not values:
            values = [clean_sentence(summary) or fallback_title]
        return " ".join(values[:5]), values[:fact_limit]

    program_title = focused_title(program_terms)
    restriction_title = focused_title(restriction_terms)
    if not program_title or not restriction_title:
        return [(title, summary, key_facts)]
    if program_title == restriction_title:
        program_title = "Apple Upgrade device-leasing program"
        restriction_title = "Apple financed-device restricted mode"
    if score_terms(restriction_title.lower(), ["apple", "苹果"]) <= 0 and not build_event_identity(restriction_title, "").products:
        restriction_title = f"苹果租赁设备：{restriction_title}"

    program_summary, program_facts = focused_content(program_terms, program_title)
    restriction_summary, restriction_facts = focused_content(restriction_terms, restriction_title)
    return [
        (program_title, program_summary, program_facts),
        (restriction_title, restriction_summary, restriction_facts),
    ]



def historical_roadmap_recap_without_current_report(title: str, summary: str, key_facts: Sequence[str]) -> bool:
    """Require a new source-owned disclosure before making roadmap children."""
    # A dated archive of already announced products and an author's outlook
    # of long-awaited rumored launches do not create a new action per link.
    if (_compiled_rule(r"\b(?:announced|released|unveiled)\s+\d+\s+(?:new\s+)?products?\s+in\s+the\s+past\s+month\b", re.I).search(title)
            and _compiled_rule(r"\b(?:previous\s+coverage|in\s+case\s+you\s+missed|recent\s+wave)\b", re.I).search(summary[:1200])):
        return True
    if (_compiled_rule(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+products?\s+launching\s+soon\b", re.I).search(title)
            and _compiled_rule(r"\b(?:rumou?red\s+product\s+unveilings?|unveilings?\s+soon|waited\s+a\s+long\s+time)\b", re.I).search(summary[:700])):
        return True
    # Publisher recaps often lead with a list of products already unveiled
    # before stating that the remaining list is only an outlook.  Keep that
    # transition in scope without treating the prior launch as a new report.
    opening = summary[:1000]
    retrospective = _compiled_rule(r"\b(?:recap(?:ped)?|summari[sz](?:e|ed))\b.{0,145}"
        r"\b(?:previously|earlier|past|rumou?rs?|expectations?|what\s+to\s+expect)\b|"
        r"\b(?:rumou?red|expected)\s+(?:products?|devices?)\s+to\s+(?:launch|arrive)\b|"
        r"(?:回顾|汇总).{0,65}(?:此前|以往|旧报道|传闻|预期)", re.I).search(opening)
    if not retrospective:
        prospective = _compiled_rule(r"即将亮相|发布前瞻|新品前瞻|launching\s+soon|what\s+to\s+expect", re.I).search(title)
        prior_rumors = any(_compiled_rule(r"此前.{0,16}(?:传闻|报道)|早前.{0,16}(?:消息|爆料)|previous(?:ly)?\s+(?:reports?|rumou?rs?)", re.I).search(fact) for fact in key_facts)
        retrospective = prospective and prior_rumors
    if not retrospective:
        # Some publisher leads promise a "latest" forecast, while the body
        # explicitly introduces an editor's preview and then walks through
        # separately dated earlier reports. The source's own stage ordering,
        # rather than its headline adjective, determines this form.
        editorial_preview = any(_compiled_rule(r"(?:小编|本文|本篇).{0,32}(?:前瞻|梳理|盘点|安排)|"
            r"\b(?:we|here['’]s)\b.{0,42}\b(?:recap|roundup|look\s+back)\b", re.I).search(fact) for fact in key_facts)
        prior_reports = sum(bool(_compiled_rule(r"(?:去年|此前|早前|今年)\s*\d{1,2}\s*月|"
            r"(?:到了|进入)\s*\d{1,2}\s*月|"
            r"\b(?:last|earlier|previous)\s+(?:year|month|spring|summer)\b", re.I).search(fact) and _compiled_rule(r"(?:报道|爆料|放料|消息|渲染图)|"
                                r"\b(?:report|rumou?r|source|render)\b", re.I).search(fact))
            for fact in key_facts)
        retrospective = editorial_preview and prior_reports >= 2
    if not retrospective:
        return False
    source = " ".join([summary, *key_facts])
    for sentence in _compiled_rule(r"(?<=[.!?])\s+|[。！？]", 0).split(source, 0):
        if _compiled_rule(r"\b(?:previously|earlier|old|past|last\s+year|historical)\b|此前|早前|以往|旧报道|历史", re.I).search(sentence):
            continue
        if _compiled_rule(r"\b(?:might|may|could|likely|rumou?red|expected|sometimes|what\s+to\s+expect)\b|"
                     r"(?:可能|预计|有望|传闻|据称)", re.I).search(sentence):
            continue
        current_disclosure = _compiled_rule(r"\b(?:today|this\s+week|now|newly)\b[^.!?]{0,80}"
            r"\b(?:reports?|disclos(?:es|ed)|confirm(?:s|ed)|announc(?:es|ed)|"
            r"develop(?:s|ed|ing)|test(?:s|ed|ing))\b|"
            r"\b(?:new|fresh)\s+(?:report|disclosure|filing|document)\b[^.!?]{0,90}"
            r"\b(?:reveals?|says?|confirms?|shows?)\b|"
            r"\b(?:apple|bloomberg|gurman)\b[^.!?]{0,50}"
            r"\b(?:announc(?:es|ed)|confirm(?:s|ed)|disclos(?:es|ed)|reports?|"
            r"introduc(?:es|ed)|launch(?:es|ed)|releas(?:es|ed)|unveil(?:s|ed))\b|"
            r"(?:今天|本周|刚刚|最新).{0,45}(?:披露|证实|宣布|公布)|"
            r"苹果(?:公司)?[^。！？]{0,35}(?:今日|今天|本周)[^。！？]{0,75}"
            r"(?:推送|发布|推出|上线)", re.I).search(sentence)
        if current_disclosure and not _compiled_rule(r"\b(?:has|have|did)\s+not\b|\bno\s+new\b|尚未|没有", re.I).search(sentence):
            return False
    return True


def project_disclosed_devices(evidence: ArticleEvidence, *, fact_limit: int):
    """Project a multi-device data leak using local subject-bearing spans.

    A shared page/code source is not a shared device action. Unowned or
    historical spans remain in the normal source remainder for review.
    """
    headline = _clean(evidence.title)
    subjects = disclosed_device_subjects(headline)
    if len(subjects) < 2 or not _compiled_rule(r"leak|曝光|泄露|爆料", re.I).search(headline):
        return []
    opening = " ".join(unit.text for unit in evidence.units[:4])
    if not _compiled_rule(r"\b(?:code|images?|artwork|icons?)\b|代码|图片", re.I).search(opening):
        return []
    groups = {subject: [] for subject in subjects}
    generations = dict(subjects)
    owner = None
    for unit in evidence.units:
        if unit.kind != "p" or unit.container_id == "caption":
            continue
        for start, end in source_sentence_spans(unit.text):
            sentence = unit.text[start:end]
            # Coordinated clauses may each assert a different device fact.
            for clause in _compiled_rule(r",\s+(?:while|whereas)\s+|；", 0).split(sentence, 0):
                named = disclosed_device_subjects(clause)
                if not named and "apple-tv" in subjects and _compiled_rule(r"\bapple\s+tv\b", re.I).search(clause):
                    named = {"apple-tv": ""}
                if len(named) > 1:
                    owner = None
                    continue
                if named:
                    owner, generation = next(iter(named.items()))
                    if generation:
                        generations[owner] = generation
                if owner not in groups:
                    continue
                if _compiled_rule(r"\b(?:previously|current(?:-gen)?|original|first-generation|last\s+year)\b|此前|现款|初代", re.I).search(clause):
                    # Keep a present new-device assertion that compares to
                    # the old model, but do not attach a standalone recap.
                    if not _compiled_rule(r"\b(?:new|next|leaked|upcoming)\b|新款|曝光", re.I).search(clause):
                        continue
                if not named and not _compiled_rule(r"^(?:it|the\s+(?:device|image|model)|this|该|这款)\b", re.I).match(clause):
                    continue
                if clause not in groups[owner]:
                    groups[owner].append(clause)
    ready = {subject: facts for subject, facts in groups.items() if facts}
    if len(ready) < 2:
        return []
    labels = {'apple-tv': 'Apple TV 4K', 'homepod-mini': 'HomePod mini',
              'ipad-mini': 'iPad mini', 'ipad-base': 'iPad'}
    return [(f"{labels[subject]}{(' ' + generations[subject]) if generations.get(subject) and subject != 'apple-tv' else ''} device leak",
             " ".join(facts[:6]), facts[:fact_limit]) for subject, facts in ready.items()]


def project_executive_visit_actions(title: str, summary: str, evidence: ArticleEvidence | None,
                                   *, fact_limit: int):
    """Separate the government's meeting from concrete local visit activities.

    Visit biography and a bare itinerary do not create a second action. Only
    current interaction/retail/creator passages support that projection.
    """
    if evidence is None:
        return []
    s = lambda pattern, text: _compiled_rule(pattern, re.I).search(text)
    opening = ' '.join(u.text for u in evidence.units[:4])
    if not s(r'apple|苹果', title + opening) or not s(r'库克|(?:tim\s*)?cook(?![a-z])|特努斯|ternus', title):
        return []
    meeting = source_executive_government_frame(title, ' '.join(u.text for u in evidence.units))
    if meeting is None:
        return []
    person = meeting.subject.split(':')[2]
    meetings, visits = [], []
    owner = ''
    for unit in evidence.units:
        if unit.kind != 'p' or unit.container_id == 'caption':
            continue
        for start, end in source_sentence_spans(unit.text):
            clause = unit.text[start:end].strip()
            if s(r'据.{0,20}昨日.{0,8}报道|此前|去年|last\s+year|previously|在担任.+期间', clause):
                owner = ''
                continue
            actors = source_executive_people(clause)
            if actors and actors != {person}:
                owner = ''
                continue
            local_meeting = source_executive_government_frame(clause, '', context_actor=person)
            if local_meeting is not None and (local_meeting.subject != meeting.subject or local_meeting.action != meeting.action):
                owner = ''
                continue
            if local_meeting is not None:
                owner = 'meeting'
            elif (s(r'喝早茶|早茶店|探班|探访|到访.{0,15}零售店|开发者交流|developers|创作|主创人员', clause)
                    and (actors == {person} or s(r'^(?:他|两人|一行)', clause))):
                owner = 'visit'
            elif s(r'业务布局|扩大.{0,15}业务|供应链协同|创新生态|制造.{0,20}合作|销售渠道|表示欢迎', clause):
                owner = 'meeting'
            elif not s(r'^他|^两人|^其中|^据了解|^除了|^此次|^库克|^蒂姆|^孟|^双方|^在广州', clause):
                owner = ''
            if owner == 'meeting':
                if clause not in meetings: meetings.append(clause)
            elif owner == 'visit':
                if clause not in visits: visits.append(clause)
    if not meetings:
        return []
    person = meeting.subject.split(':')[2]
    name = person.replace('-', ' ').title()
    # The identity resolver already owns the counterpart and phase. Keep the
    # source headline instead of inventing a role from its opaque subject key.
    variants = [(title, ' '.join(meetings[:6]), meetings[:fact_limit])]
    if visits:
        # Prefer an explicitly named destination; this does not infer a visit
        # from the government's location or the executive's biography.
        location = next((key for key, pattern in (('Guangzhou', r'广州|guangzhou'), ('Shanghai', r'上海|shanghai'),
            ('Beijing', r'北京|beijing'), ('Shenzhen', r'深圳|shenzhen')) if s(pattern, ' '.join(visits) + ' ' + opening)), '')
        if location:
            variants.append((f'Apple executive {name} visited {location}', ' '.join(visits[:6]), visits[:fact_limit]))
    return variants


def project_compound_article(title: str, summary: str, key_facts: list[str], *,
        identity: EventIdentity, headline_identity: EventIdentity, fact_identities: Iterable[EventIdentity],
        release_clauses: Sequence[tuple[str, EventIdentity]], release_facts: Iterable[tuple[str, EventIdentity]],
        fact_limit: int, single_mockup: bool, catalog_withdrawal: bool,
        restricted_clarification: bool, trailer_evidence: bool,
        evidence: ArticleEvidence | None = None) -> list[tuple[str, str, list[str]]]:
    """One projection order, using prepared source identities and parent forms."""
    original = [(title, summary, key_facts)]
    if identity.content_form in {"podcast", "poll"} or source_editorial_evaluation(title, summary):
        return original
    if source_editorial_outlook(title, summary, tuple(u.text for u in evidence.units) if evidence else tuple(key_facts)):
        return original
    if historical_roadmap_recap_without_current_report(title, summary, key_facts):
        return original
    if single_mockup:
        return original
    if source_disclosure_bundle(title, summary, tuple(key_facts)) is not None:
        return original
    passages = tuple(u.text for u in evidence.units) if evidence else tuple(key_facts)
    dated = source_dated_launch_frame(title, summary, passages, identity)
    if dated is not None:
        operation = source_operation_frame(title, summary, tuple(key_facts), identity, source_units=passages)
        if operation is not None and operation.action == dated.action:
            return original
    if source_leadership_interview_frame(title, summary, passages) is not None:
        return original
    executive_actions = project_executive_visit_actions(title, summary, evidence, fact_limit=fact_limit)
    if executive_actions:
        return executive_actions
    inventory = project_current_release_inventory(title, summary, evidence, fact_limit)
    if inventory:
        return inventory
    variants = project_os_release_variants(title, summary, key_facts, clauses=release_clauses, facts=release_facts, fact_limit=fact_limit, evidence=evidence)
    if len(variants) > 1:
        return variants
    if restricted_clarification:
        return original
    if evidence is not None:
        device_sections = project_disclosed_devices(evidence, fact_limit=fact_limit)
        if device_sections:
            return device_sections
        source_sections = project_content_source_sections(evidence, title, summary, fact_limit=fact_limit)
        if source_sections:
            return source_sections
    claims = project_multi_subject_apple_silicon_claims(title, summary, key_facts)
    if claims:
        return [(claim.title, claim.summary, list(claim.key_facts)) for claim in claims]
    variants = project_smart_home_roadmap(title, summary, key_facts, fact_limit=fact_limit, evidence=evidence)
    if variants != original:
        return variants
    variants = project_title_content_announcements(title, summary, key_facts, identity=identity, fact_limit=fact_limit, trailer_evidence=trailer_evidence)
    if len(variants) > 1:
        return variants
    claims = project_first_party_content_claims(title, summary, key_facts)
    if claims:
        return [(claim.title, claim.summary, list(claim.key_facts)) for claim in claims]
    variants = project_numbered_service_announcements(title, summary, key_facts, identity=identity, fact_limit=fact_limit)
    if len(variants) > 1:
        return variants
    variants = project_hardware_roadmap(title, summary, key_facts, identity=identity, single_source_disclosure=catalog_withdrawal or single_mockup, fact_limit=fact_limit, evidence=evidence)
    if variants != original:
        return variants
    variants = project_multi_family_iphone_report(title, summary, key_facts, fact_limit=fact_limit)
    if len(variants) > 1:
        return variants
    variants = project_compound_product_actions(title, summary, key_facts, identity=identity, headline_identity=headline_identity, fact_identities=fact_identities, fact_limit=fact_limit)
    if len(variants) > 1:
        return variants
    return _project_device_finance_claims(title, summary, key_facts, identity=identity, fact_limit=fact_limit)


def focus_source_roundup(title: str, summary: str, key_facts: list[str], *,
        parent_is_roundup: bool, items: Sequence[tuple[str, str]], fact_limit: int) -> tuple[str, str, list[str]]:
    """Keep the original semantic roundup view alongside lossless raw evidence."""
    if not parent_is_roundup:
        return title, summary, key_facts
    focused, seen = [], set()
    for text, source_tier in items:
        if source_tier in {"strong", "ecosystem"}:
            add_unique_text(focused, seen, text)
    if not focused:
        return title, summary, key_facts
    return roundup_title_from_item(focused[0]), " ".join(focused[:5]), focused[:fact_limit]


def locate_source_facts(evidence: ArticleEvidence, facts: Sequence[str]) -> tuple[tuple[str, int, int], ...]:
    """Locate selected source text without inventing claim identities or offsets."""
    spans = set()
    for fact in facts:
        if not fact:
            continue
        for unit in evidence.units:
            cursor = 0
            while (start := unit.text.find(fact, cursor)) >= 0:
                spans.add((unit.unit_id, start, start + len(fact)))
                cursor = start + len(fact)
    return tuple(sorted(spans))


def attributed_content_synopsis_subject(units: Sequence, index: int) -> str | None:
    if index == 0 or units[index].kind != "p":
        return None
    introduction = units[index - 1].text
    if not _compiled_rule(r"what\s+to\s+expect|synopsis|plot\s+of|故事梗概|剧情简介", re.I).search(introduction):
        return None
    quoted = _compiled_rule(r"[“\"]([^”\"]{3,100})[”\"]|[‘']([^’']{3,100})[’']", 0).search(introduction)
    return next((part for part in quoted.groups() if part), "").casefold() if quoted else None


def projected_source_dispositions(evidence: ArticleEvidence, child_facts: Sequence[Sequence[str]],
                                  source_facts: Sequence[str]):
    """Retain the selected source facts and unhandled current source actions."""
    history_units = release_history_unit_ids(evidence)
    assigned = [[span for span in locate_source_facts(evidence, facts) if span[0] not in history_units]
                for facts in child_facts]
    # A publisher can introduce an attributed synopsis of the very work whose
    # trailer was selected. It supports that action; it is not a second launch.
    # Bind only a named work found in a child's located source facts, so a
    # neighboring show's synopsis never inherits this child's provenance.
    editorial_units = editorial_list_unit_ids(evidence)
    for index, unit in enumerate(evidence.units[1:], start=1):
        if unit.kind != "p" or unit.unit_id in editorial_units:
            continue
        subject = attributed_content_synopsis_subject(evidence.units, index)
        if not subject:
            continue
        matches = [child_index for child_index, (facts, spans) in enumerate(zip(child_facts, assigned))
                   if spans and any(subject in fact.casefold() for fact in facts)]
        if len(matches) != 1:
            continue
        child = matches[0]
        pending_start = pending_end = None
        for start, end in source_sentence_spans(unit.text):
            sentence = unit.text[start:end].strip()
            other_work = _compiled_rule(r"[“\"]([^”\"]{3,100})[”\"]|[‘']([^’']{3,100})[’']", 0).search(sentence)
            excluded = (sentence.endswith(("?", "？")) or inline_media_marker_spans(sentence)
                    or _compiled_rule(r"^(?:subscribe|sign\s+up|watch|stream|listen|read|"
                                r"click|visit|learn\s+more|see\s+more|follow)\b", re.I).match(sentence)
                    or _compiled_rule(r"\b(?:per\s+month|free\s+trial|subscription|pricing)\b|"
                                 r"[$£€]\s*\d", re.I).search(sentence)
                    or (other_work and subject not in next((part for part in other_work.groups() if part), "").casefold()
                        and _compiled_rule(r"\b(?:show|series|season|film|movie|trailer|teaser|premier)\b", re.I).search(sentence))
                    or (subject not in sentence.casefold()
                        and high_confidence_direct_apple_action(build_event_identity(sentence, ""))))
            if excluded:
                if pending_start is not None:
                    assigned[child].append((unit.unit_id, pending_start, pending_end))
                    pending_start = pending_end = None
                continue
            if pending_start is None:
                pending_start = start
            pending_end = end
        if pending_start is not None:
            assigned[child].append((unit.unit_id, pending_start, pending_end))
    assigned = tuple(tuple(dict.fromkeys(spans)) for spans in assigned)
    remaining, excluded = source_evidence_remainder(evidence, [span for spans in assigned for span in spans])
    selected = locate_source_facts(evidence, source_facts)
    units = {unit.unit_id: unit for unit in evidence.units}
    predictions = {key: adjacent_unattributed_prediction_spans(units[key].text)
                   for key in {span[0] for span in remaining}}
    visible, exclusions, seen = [], list(excluded), set()
    for key, start, end in remaining:
        text = units[key].text[start:end]
        selected_context = any(unit_key == key and left < end and start < right for unit_key, left, right in selected)
        current_action = high_confidence_direct_apple_action(build_event_identity(text, ""))
        attribution_review = any(start < right and left < end for left, right in predictions[key])
        if selected_context or current_action or attribution_review or source_apple_invitation_fact(text):
            if text not in seen:
                visible.append((key, start, end))
                seen.add(text)
            else:
                exclusions.append((key, start, end, "Repeated source statement already retained in local review"))
        else:
            exclusions.append((key, start, end, "Source context outside the selected fact view and explicit current Apple actions"))
    return assigned, tuple(visible), tuple(exclusions)
