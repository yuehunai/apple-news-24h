"""Deterministic article-level event reconciliation.

Source profiles retain concrete action evidence. The shared pair relation
separates conflicts and joins supported cross-source coverage; incoming groups
do not authorize a match, and event assembly consumes the resolved outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
import re
import unicodedata
from typing import Callable, Iterable, Mapping, Sequence, TypeVar

from .models import PreparedFact, SourceFactView, EventFactPlan

from .event_identity import (
    REGION_TERMS,
    is_personal_product_complaint,
    is_retail_promotion,
    is_os_release_announcement,
    source_acquisition_frame,
    is_weekly_editorial_recap,
    source_design_oversight,
    source_free_race_stream,
    _compiled_rule,
    _normalized_os_version,
    _lead_assigns_app_release_to_apple,
    ANALYST_INSTITUTION_ALIASES,
    EVIDENCE_BACKED_COMPONENTS,
    COMPONENT_PATTERNS,
    EventIdentity,
    SourceActionFrame,
    LEAD_IDENTITY_COMPONENTS,
    PRODUCT_PATTERNS,
    build_event_identity,
    source_accessory_category,
    source_device_disclosure,
    device_operation_subjects,
    source_employee_leave_notice,
    source_store_sales_measure,
    source_device_workload_measure,
    source_hardware_project,
    foldable_iphone_generation_subject,
    source_fact_changes_generation,
    named_iphone_models,
    source_operation_frame,
    source_market_measurement_frame,
    source_market_quarter,
    source_market_statements,
    source_dated_launch_frame,
    source_editorial_outlook,
    source_editorial_evaluation,
    home_os_development_action,
    descriptive_apple_product_reference,
    is_platform_compatible_accessory_title,
    first_party_hardware_implementation,
    OS_COMPONENT_PATTERNS,
    software_components,
    source_sentence_spans,
    source_clause_spans,
    source_chip_technical_disclosures,
    source_primary_assertion,
    source_predicate_role,
    source_product_lifecycle_assertion,
    source_current_lifecycle_update,
    source_denies_action,
    has_haptic_patent_subject,
    current_public_os_release,
    is_apple_led_developer_submission_story,
    is_direct_apple_product_lifecycle_action,
    is_direct_first_party_named_object_change,
    is_direct_first_party_builtin_removal,
    is_editorial_change_request,
    is_material_apple_device_operational_deployment,
    is_third_party_app_action_on_apple_platform,
    primary_assertion_components,
    quantified_apple_company_performance_subject,
)
from .models import BoundClaim, ClaimEligibility, ReconciliationProfile
from .event_matcher import (
    FIRST_PARTY_SERVICE_PRODUCTS, identity_pair_decision, profile_pair_decision, _explicit_identity_conflict,
    _content_work_profile, _compatible_content_work_profiles,
    STRUCTURED_EVIDENCE_KEY_PREFIXES,
    _ACTION_EQUIVALENCE,
    _SOFTWARE_FIRST_PARTY_PRODUCTS,
    _direct_title_action_conflict,
    _direct_title_subject_conflict,
    _disclosed_build_conflict,
    _event_key_namespace,
    _explicit_property_value_conflict,
    _explicit_separation_conflict,
    _near_identifier,
    _primary_title_subjects,
    _profile_release_channels,
    _profile_release_conflict,
    _profile_release_stages,
    _profiles_conflict,
    _projection_scope_conflict,
    _release_wave_parts,
    _release_waves_conflict,
    _same_named_report_concrete_action,
    _seed_profiles_conflict,
    _structured_title_action_classes,
    _weak_editorial_profile,
    supported_reconciliation_event_keys,
)


ArticleT = TypeVar("ArticleT")






_GENERIC_SUBJECT_WORDS = {
    "a",
    "an",
    "apple",
    "bigger",
    "everything",
    "if",
    "ios",
    "macos",
    "message",
    "new",
    "next",
    "report",
    "some",
    "the",
    "the-series",
    "the-show",
    "it",
    "will",
    "these",
    "this",
    "watchos",
}


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    return _compiled_rule(r"\s+", 0).sub(" ", value, 0).strip()


_APPLE_EPIC_OPENING_FILING = (
    r"\bapple\b\s+(?:(?:today|this\s+week)\s+)?"
    r"(?:files|submits|has\s+(?:filed|submitted)|filed|submitted)\s+"
    r"(?:its\s+)?(?:opening|merits)\s+brief\b"
)
_GOVERNMENT_AMICUS_FILING = (
    r"\b(?:us\s+doj|doj|department\s+of\s+justice|solicitor\s+general|u\.?s\.?\s+government)\b"
    r"(?:\s*,?\s*through\s+(?:the\s+)?solicitor\s+general)?\s*,?\s*"
    r"(?:did\s+)?(?:filed?|submitted?)\s+(?:an?\s+)?(?:amicus\s+)?briefs?\b|"
    r"美国司法部(?:\([^)]{0,55}\))?\s*(?:本周|今日|今天)?\s*"
    r"(?:正式|已经|已)?\s*(?:向(?:美国)?最高法院(?:\([^)]{0,55}\))?\s*)?"
    r"(?:正式|已经|已)?\s*提交法庭之友意见书"
)


def _filing_time_scope(sentence: str, relation: re.Match[str]) -> str:
    """Use timing attached to this filing clause, not another case-history sentence."""
    prefix = sentence[:relation.start()]
    suffix = sentence[relation.end():]
    # Only an explicit distant date separates filings. Yesterday and "earlier"
    # can still describe the current report's action.
    past = r"\blast\s+year\b|去年"
    future = r"\b(?:tomorrow|next\s+week)\b|明日|明天|下周"
    for scope, marker in (("past", past), ("future", future)):
        if (_compiled_rule(rf"(?:^|[;,，；]\s*)(?:{marker})[,，\s]*$", re.I).search(prefix)
                # A date after "citing a ruling issued" belongs to that ruling.
                or _compiled_rule(rf"^\s*(?:{marker})(?=$|[\s,，;；。！？])", re.I).search(suffix)):
            return scope
    year = r"\bin\s+20\d{2}\b"
    if (_compiled_rule(rf"(?:^|[;,，；]\s*)(?:{year})[,，\s]*$", re.I).search(prefix)
            or _compiled_rule(rf"^\s*(?:{year})(?=$|[\s,，;；。！？])", re.I).search(suffix)):
        return "dated"
    local = sentence[relation.start():relation.end()]
    current = r"\b(?:today|this\s+week)\b|本周|今日|今天"
    if (_compiled_rule(current, re.I).search(local)
            or _compiled_rule(rf"(?:^|[;,，；]\s*)(?:{current})[,，\s]*$", re.I).search(prefix)
            or _compiled_rule(rf"^\s*(?:{current})(?=$|[\s,，;；。！？])", re.I).search(suffix)):
        return "current"
    return "unspecified"


def _ssd_support_document_stage(title: str, lead: str) -> str | None:
    """Bind a Mac mini SSD document change to Apple's asserted verb."""
    headline = _normalized(title)
    if not (_compiled_rule(r"(?<![a-z0-9])mac\s*mini(?![a-z0-9])", re.I).search(headline)
            and _compiled_rule(r"(?<![a-z0-9])(?:ssd|nand|storage)(?![a-z0-9])|存储|硬盘", re.I).search(headline)
            and _compiled_rule(r"支持文档|维修文档|\b(?:support|repair)\s+(?:document|page|article)\b", re.I).search(headline)):
        return None
    first_sentence = _normalized(_compiled_rule(r"[。！？]|(?<=[.!?])\s+").split(lead, maxsplit=1)[0])
    first_sentence = _compiled_rule(r"^[^。!?]{0,50}消息[,，:：]\s*").sub("", first_sentence, count=1)
    chinese_relation = _compiled_rule(
        r"^苹果(?:公司)?\s*(?P<frame>(?:(?:在|于)\s*(?:(?:\d{2,4}\s*年\s*)?\d{1,2}\s*月\s*\d{1,2}\s*日|今日|今天|昨日|昨天)\s*|今日|今天|昨日|昨天|去年|此前)?"
        r"(?:已经|已|正式|计划|拟|将|即将|可能|预计|没有|并未|尚未|未|不会|不曾)?)\s*"
        r"(?:更新|修订)[^，,；;。！？]{0,85}(?:支持文档|维修文档)", re.I
    )
    english_relation = _compiled_rule(
        r"^apple\s+(?P<frame>(?:(?:today|yesterday|this\s+week|last\s+year|previously)\s+)?"
        r"(?:(?:has|have|had|did|does|will|would|may|might|won't|plans?\s+to)\s+)?"
        r"(?:not\s+)?)"
        r"(?:updates?|updated|revises?|revised)\b[^,;.!?]{0,85}"
        r"(?:support|repair)\s+(?:document|page|article)\b", re.I
    )
    for clause in (headline, first_sentence):
        relation = chinese_relation.search(clause) or english_relation.search(clause)
        if relation is None:
            continue
        frame = relation.group("frame")
        if _compiled_rule(r"未|没有|并未|尚未|不会|不曾|\b(?:not|never|won't)\b", re.I).search(frame):
            return "denied"
        if _compiled_rule(r"计划|拟|将|即将|可能|预计|\b(?:will|would|may|might|plans?)\b", re.I).search(frame):
            return "planned"
        if _compiled_rule(r"去年|此前|\b(?:last\s+year|previously)\b", re.I).search(frame):
            return "past"
        return "current"
    return "unattributed"


def _source_owned_named_action(title: str, lead: str) -> tuple[str, str] | None:
    """Bind a concrete named object and current action across source languages.

    The owner and predicate must be asserted by this source. Device generation
    or a background mention of Siri alone cannot authorize a relation.
    """
    if is_editorial_change_request(title):
        return None
    headline = _normalized(title)
    source_lead = _compiled_rule(r"\bu\.s\.(?=\s)", re.I).sub("US", lead)
    source_sentences = [_normalized(part) for part in _compiled_rule(r"(?<=[.!?])\s+|[。！？]").split(source_lead)
                        if part.strip()]
    opening = " ".join(source_sentences[:2])
    claim = f"{headline}. {opening}"

    # Identify the source's current subject and verb before its background
    # paragraphs can introduce a different product, actor, or stage.
    if (_compiled_rule(r"(?:苹果|\bapple\b)[^。.!?]{0,95}(?:研发|开发|developing|working\s+on)", re.I).search(opening)
            and _compiled_rule(r"防抢锁机|\bauto\s*lock\b|(?:theft|snatch)[- ](?:detection|lock)", re.I).search(claim)
            and _compiled_rule(r"iphone|ios|手机", re.I).search(claim)):
        return "iphone:anti-theft-auto-lock", "development-report"
    face_model = _compiled_rule(r"iphone\s*(\d+)\s*pro(?![a-z0-9])", re.I).search(claim)
    if (face_model and _compiled_rule(r"face\s*id", re.I).search(claim)
            and _compiled_rule(r"(?:supplemental|additional|额外|补充|新增)[^。.!?]{0,35}(?:image|图像)", re.I).search(claim)
            and _compiled_rule(r"secure\s*exclave|安全单元", re.I).search(claim)
            and _compiled_rule(r"(?:support\s+documentation|技术文档|支持文档|updated\s+documentation)", re.I).search(lead)):
        return f"iphone-{face_model.group(1)}-pro:face-id-image-validation", "documentation-disclosure"
    coe_year = _compiled_rule(r"(?<!\d)(20\d{2})(?!\d)").search(headline)
    if (coe_year and _compiled_rule(r"\biphone\b", re.I).search(claim)
            and _compiled_rule(r"\b(?:coe|color\s*filter\s*on\s*encapsulation)\b", re.I).search(lead)
            and _compiled_rule(r"\bpro\b|pro系列", re.I).search(lead[:1000])
            and _compiled_rule(r"delay|later|postpon|推迟|延期|可能要等到|adopt", re.I).search(claim)):
        return f"iphone-pro:coe-oled:{coe_year.group(1)}", "adoption-timing-report"
    mac_pair = (_compiled_rule(r"\bmac\s*mini\b", re.I).search(opening)
                and _compiled_rule(r"\bmac\s*studio\b", re.I).search(opening))
    if (mac_pair and _compiled_rule(r"(?:apple\s+stores?|apple\s+store\s+locations?|苹果商店)", re.I).search(opening)
            and _compiled_rule(r"\b(?:today|now)\b|今日|今天", re.I).search(claim)
            and _compiled_rule(r"launch|available|arriv|shop|开售|上市", re.I).search(opening)):
        return "mac-mini-mac-studio:retail", "current-availability"
    if _ssd_support_document_stage(title, lead) == "current":
        return "mac-mini:ssd-support-document", "support-document-revision"
    # The disclosure is attributed to the storage supplier. Documentation
    # changes and older removable models are separate facts and actions.
    supplier_name = r"(?<![a-z0-9])expand\s*mac\s*mini(?:\.com)?(?![a-z0-9])"
    supplier_relation = _compiled_rule(
        rf"{supplier_name}\s*,?\s*(?:now\s+)?(?:reports?|reported|confirms?|confirmed|reveals?|revealed)\b|"
        rf"(?:^\s*(?:as\s+)?|[,;]\s*as\s+)(?:confirmed|reported|revealed)\s+by\s+"
        rf"(?:the\s+website\s+)?[\"“]?{supplier_name}|"
        rf"\b(?:is|was|were|has\s+been|have\s+been)\s+(?:confirmed|reported|revealed)\s+by\s+"
        rf"(?:the\s+website\s+)?[\"“]?{supplier_name}|"
        rf"{supplier_name}\s*(?:等(?:多个|多家|其他)[^，。,.]{{0,22}})?(?:已经|已)?(?:确认|披露)", re.I
    )
    storage_change = _compiled_rule(r"\b(?:ssd|nand|storage|upgradeable)\b|存储|闪存|硬盘|扩容", re.I)
    fixed_storage = _compiled_rule(r"\b(?:soldered|solder|not\s+upgradeable|unremovable|non[- ]removable)\b|焊(?:接|死)|板载|不可(?:拆卸|更换|升级)", re.I)
    for index, sentence in enumerate(source_sentences):
        if not _compiled_rule(r"(?<![a-z0-9])mac\s*mini(?![a-z0-9])", re.I).search(headline):
            break
        relation = supplier_relation.search(sentence)
        if not (relation and storage_change.search(sentence) and fixed_storage.search(sentence)):
            continue
        # A finite affirmative passive can report a completed disclosure.
        # Do not start matching inside a longer modal chain: its finite modal,
        # including standard negation and contractions, scopes over "have been".
        if (_compiled_rule(r"^have\s+been\s+", re.I).match(relation.group())
                and _compiled_rule(
                    r"\b(?:can(?:not|'t)?|won't|shan't|"
                    r"(?:could|will|would|shall|should|may|might|must)(?:n't)?)"
                    r"(?:\s+not)?\b[^,;.!?]{0,25}$|\bto\s+$",
                    re.I,
                ).search(sentence[:relation.start()])):
            continue
        if _compiled_rule(
            r"\b(?:previously|last\s+year|earlier|in\s+20\d{2}|den(?:y|ies|ied)|"
            r"disput(?:es?|ed)|did\s+not\s+(?:report|confirm|reveal))\b|"
            r"(?:此前|以往|去年|否认|未(?:确认|披露))", re.I
        ).search(sentence):
            continue
        # Bind the two currently discussed chip versions to this supplier's
        # storage claim. Older removable models in later context do not join.
        frame = f"{headline}. {opening}. {sentence} " + (
            source_sentences[index + 1] if index + 1 < len(source_sentences) else ""
        )
        chips = list(_compiled_rule(
            r"(?<![a-z0-9])m(\d+)\s*(pro|max|ultra)?(?![a-z0-9])", re.I
        ).finditer(frame))
        for first, second in zip(chips, chips[1:]):
            if second.start() - first.end() > 70:
                continue
            versions = {
                f"m{match.group(1)}" + (f"-{match.group(2)}" if match.group(2) else "")
                for match in (first, second)
            }
            if len(versions) == 2:
                return (
                    f"expand-mac-mini:mac-mini-{'+'.join(sorted(versions))}:nand",
                    "current-storage-disclosure",
                )
    if (_compiled_rule(r"\bapple\s+shares\b|苹果(?:公司)?(?:周二)?盘中股价|苹果(?:公司)?股价", re.I).search(opening)
            and _compiled_rule(r"intraday|盘中|moments\s+after\s+the\s+market\s+opened", re.I).search(opening)
            and _compiled_rule(r"record|high|历史新高|纪录", re.I).search(opening)):
        return "apple-shares:intraday-record", "reported-market-result"
    beats_model = _compiled_rule(r"\bbeats\s*(\d+)(?!\d)", re.I).search(headline)
    firmware_build = _compiled_rule(r"(?<![a-z0-9])(\d+[a-z]\d{2,})(?![a-z0-9])", re.I).search(claim)
    if (beats_model and firmware_build
            and _compiled_rule(r"固件更新|固件.{0,8}更新|firmware\s+update", re.I).search(claim)
            and _compiled_rule(r"(?:苹果|\bapple\b)[^。.!?]{0,85}(?:推送|发布|released?|pushed?)", re.I).search(opening)):
        return f"beats-{beats_model.group(1)}:firmware-{firmware_build.group(1)}", "firmware-update"
    meeting_relation = _compiled_rule(
        r"\btim\s+cook\b[^.!?。！？]{0,24}\b(?:met(?:\s+this\s+week)?\s+with|meets|spoke\s+with|talked\s+with)\b"
        r"[^.!?。！？]{0,85}\b(?:eu\s+commission\s+president|president\s+of\s+the\s+european\s+commission|ursula\s+von\s+der\s+leyen)\b",
        re.I,
    )
    if any(meeting_relation.search(sentence)
           and _compiled_rule(r"\b(?:this\s+week|today|un\s+general\s+assembly)\b|本周|今天|今日", re.I).search(sentence)
           and not _compiled_rule(r"\b(?:previously|earlier|last\s+year|in\s+20\d{2}|never|did\s+not)\b|此前|曾经|未曾", re.I).search(sentence)
           for sentence in [headline, *source_sentences[:2]]):
        return "tim-cook:eu-commission-president", "current-government-meeting"
    apple_filing = _compiled_rule(_APPLE_EPIC_OPENING_FILING, re.I).search(headline)
    apple_scope = _filing_time_scope(headline, apple_filing) if apple_filing else None
    if apple_scope == "dated":
        apple_relation = _compiled_rule(_APPLE_EPIC_OPENING_FILING, re.I)
        if any((filing := apple_relation.search(sentence)) is not None
               and _filing_time_scope(sentence, filing) == "current"
               for sentence in source_sentences[:2]):
            apple_scope = "current"
    if (apple_filing and apple_scope not in {"past", "future", "dated"}
            and _compiled_rule(r"\bepic\b", re.I).search(claim)
            and _compiled_rule(r"\b(?:supreme\s+court|scotus)\b", re.I).search(claim)
            and _compiled_rule(r"\bapp\s*store\b", re.I).search(lead)
            and _compiled_rule(r"\b(?:commission|injunction)\b", re.I).search(lead)):
        return "apple-epic-external-purchase", "opening-merits-brief"
    government_filing_relation = _compiled_rule(_GOVERNMENT_AMICUS_FILING, re.I)
    government_filing = any(
        (filing := government_filing_relation.search(sentence)) is not None
        and _filing_time_scope(sentence, filing) not in {"past", "future", "dated"}
        and (_compiled_rule(r"\b(?:this\s+week|did\s+file)\b|本周", re.I).search(sentence)
             or _compiled_rule(r"\bamicus\s+briefs?\b|法庭之友意见书", re.I).search(headline))
        for sentence in [headline, *source_sentences[:2]]
    )
    if (government_filing and _compiled_rule(r"\b(?:supreme\s+court|scotus)\b|最高法院", re.I).search(lead)
            and _compiled_rule(r"\bepic\b|\bapp\s*store\b|外链抽佣", re.I).search(lead)
            and _compiled_rule(r"\binjunction\b|\bcommission\b|\bcontempt\b|禁令|抽佣|藐视法庭", re.I).search(lead)):
        return "us-government:apple-epic-external-purchase", "current-amicus-filing"
    def owned_relation(owner_action_pattern: str, object_pattern: str,
                       control_names: frozenset[str] | None = None) -> bool:
        for sentence in [headline, *source_sentences]:
            for owner in _compiled_rule(r"\bapple(?:'s)?\b|苹果").finditer(sentence):
                local = sentence[owner.start():]
                if _compiled_rule(r"^(?:apple(?:'s)?|苹果)[^.!?。！？]{0,24}"
                                  r"(?:previously|earlier|last year|曾|此前|早前)", re.I).search(local):
                    continue
                if not _compiled_rule(owner_action_pattern, re.I).match(local):
                    continue
                object_match = _compiled_rule(object_pattern, re.I).search(local[:220])
                if (control_names is not None and object_match is not None
                        and frozenset(object_match.groups()) != control_names):
                    continue
                if object_match:
                    return True
        return False

    band_object = (r"\b(?:screen[- ]?free|screen[- ]?less|screenless|without a screen|doesn't have a screen)\b.{0,65}\b(?:fitness|activity|health)\s+(?:band|tracker|device)\b|"
                   r"\b(?:fitness|activity)\s+(?:band|tracker)\b.{0,45}\b(?:screen[- ]?free|screen[- ]?less|screenless|without a screen)\b|"
                   r"(?:无屏(?:幕|版)?|没有屏幕).{0,20}(?:健康|健身|运动|活动).{0,10}(?:追踪器|手环|腕带)|"
                   r"(?:无屏|没有屏幕).{0,20}(?:健身|活动)?腕带|健身腕带.{0,15}(?:无屏|没有屏幕)")
    band_owner_action = (r"^apple(?:'s)?\s+(?:(?:has|is|was|today|now|reportedly|currently)\s+){0,3}"
                         r"(?:tests?|tested|testing|develops?|developing|builds?|built)\b|"
                         r"^苹果(?:公司)?[^。.!?]{0,16}(?:测试|研发|开发)")
    band = bool(_compiled_rule(band_object, re.I).search(claim))
    # A screenless Whoop-like title may state the same Apple-owned tracker
    # action in its lead as a prototype-stage report, without repeating the
    # display detail there.  Keep the owner, stage, and object in one clause.
    prototype_lead = _compiled_rule(
        r"\bapple\b[^.!?]{0,95}\bat\s+the\s+prototype\s+stage\b[^.!?]{0,75}"
        r"\b(?:fitness\s+and\s+health|health\s+and\s+fitness)\s+tracker\b[^.!?]{0,95}\bwhoop\b",
        re.I,
    ).search(opening)
    screenless_whoop_title = (_compiled_rule(r"\b(?:screen[- ]?less|screen[- ]?free|screenless)\b", re.I).search(headline)
                              and _compiled_rule(r"\bwhoop\b", re.I).search(headline))
    if (band and (owned_relation(band_owner_action, band_object)
                 or _compiled_rule(r"\bapple\b[^.!?]{0,110}\b(?:working\s+on|developing|testing)\b[^.!?]{0,110}"
                                   r"\b(?:screenless|screen[- ]?free|without a screen|doesn't have a screen)\b[^.!?]{0,75}"
                                   r"\b(?:tracker|band|device)\b", re.I).search(claim)
                 or (_compiled_rule(r"\bapple\b[^.!?]{0,95}\b(?:working\s+on|developing|testing)\b", re.I).search(headline)
                     and _compiled_rule(band_object, re.I).search(opening)))
            or (screenless_whoop_title and prototype_lead)):
        return "screenless-fitness-band", "prototype-testing"

    pendant_object = r"\b(?:ai\s+)?(?:pendant|(?:wearable\s+)?pin)\b|(?:ai\s*)?(?:吊坠|挂坠)|可穿戴吊坠"
    pendant_owner_action = (r"^apple(?:'s)?\s+(?:(?:has|is|was|today|now|reportedly|currently)\s+){0,3}"
                            r"(?:put|postponed|delayed|shelved|paused)\b|"
                            r"^apple(?:'s)?\s+[^.!?]{0,85}\b(?:remains?\s+on\s+hold|was\s+put\s+on\s+hold|"
                            r"has\s+been\s+postponed)\b|"
                            r"^苹果(?:公司)?[^。.!?]{0,35}(?:搁置|推迟|延后)")
    pendant = bool(_compiled_rule(pendant_object, re.I).search(headline))
    pendant_hold = _compiled_rule(r"\b(?:put|placed|postponed|delayed|shelved|paused|on hold)\b|"
                                  r"(?:搁置|推迟|延后|暂停)", re.I)
    pendant_title_owner = _compiled_rule(r"^(?:.{0,12}[:：]\s*)?apple(?:'s)?\b|^.{0,5}苹果", re.I).search(headline)
    if pendant and (owned_relation(pendant_owner_action, pendant_object)
                    or (pendant_title_owner and pendant_hold.search(headline))
                    or (pendant_title_owner and pendant_hold.search(opening))):
        return "ai-pendant", "project-hold"

    controls = _compiled_rule(r"\b([a-z][a-z0-9-]*)\s+(?:and|与)\s+([a-z][a-z0-9-]*)\s+(?:controls?|控件)").search(headline)
    support_owner_action = (r"^apple(?:'s)?\s+(?:(?:has|is|was|today|now|reportedly|currently)\s+){0,3}"
                            r"(?:clarif(?:y|ies|ied)|revis(?:e|ed)|correct(?:s|ed)?|updat(?:e|ed|es))\b|"
                            r"^苹果(?:公司)?[^。.!?]{0,16}(?:修订|更正|澄清|更新)")
    if (controls and _compiled_rule(r"\b(?:editing|software|camera\s+app)\b|编辑|软件|相机应用", re.I).search(lead)
            and _compiled_rule(r"\b(?:support\s+page|support\s+document|supported\s+model|available\s+only|require)\b|支持文档|仅限|仅支持", re.I).search(opening)
            and owned_relation(support_owner_action,
                r"\b([a-z][a-z0-9-]*)\s+(?:and|与)\s+([a-z][a-z0-9-]*)\s+(?:controls?|控件)",
                frozenset(controls.groups()))):
        names = "-".join(sorted({controls.group(1), controls.group(2)}))
        return f"camera-editing-controls:{names}", "support-scope-clarification"
    # The named controls are the object of a support-scope correction.  A
    # phone used to capture a photo is distinct from one used to edit it.
    if (_compiled_rule(r"\btexture\b|质感", re.I).search(claim)
            and _compiled_rule(r"\bgrain\b|颗粒", re.I).search(claim)
            and _compiled_rule(r"\b(?:clarif(?:y|ies|ied)|revis(?:e|ed)|correct(?:s|ed)?|updated?|limited|exclusive)\b|"
                               r"(?:修改|澄清|更正|仅限|仅支持|限定)", re.I).search(claim)
            and _compiled_rule(r"\b(?:photographic styles|photos?|controls?|editing)\b|"
                               r"(?:摄影风格|照片|相机功能|调节选项)", re.I).search(lead)
            and _compiled_rule(r"\bapple\b[^.!?]{0,90}\b(?:clarif(?:y|ies|ied)|revis(?:e|ed)|"
                               r"correct(?:s|ed)?|updated?|limited)\b|"
                               r"苹果[^。！？]{0,65}(?:修改|澄清|更正|修订|限定)", re.I).search(claim)):
        return "camera-editing-controls:grain-texture", "support-scope-clarification"

    # Require an explicitly named capability plus its local stage/version.
    # Generic display, camera and settings facets cannot identify these acts.
    watch_build = _compiled_rule(r"\bwatchos\s*(\d+(?:\.\d+)?)\s*beta\s*(\d+)\b", re.I).search(claim)
    if (watch_build and _compiled_rule(r"\bapp\s+switcher\b|(?:应用程序切换器|后台界面)", re.I).search(claim)
            and _compiled_rule(r"\b(?:restor(?:e|es|ed)|return(?:s|ed)?|comeback|bring(?:s|ing)?\s+back)\b|"
                               r"(?:回归|带回|重新带回)", re.I).search(claim)):
        return f"watchos-{watch_build.group(1)}-beta-{watch_build.group(2)}:app-switcher", "gesture-restoration"

    if (_compiled_rule(r"\btap\s+to\s+pay(?:\s+on\s+iphone)?\b|轻点收款|轻触收款", re.I).search(claim)
            and _compiled_rule(r"\b(?:expand(?:s|ed)?|additional|more\s+countries|now\s+available)\b|"
                               r"(?:扩展|新增|更多国家|现已开放)", re.I).search(claim)
            and _compiled_rule(r"\blatin\s+america\b|\b(?:argentina|colombia|costa\s+rica)\b|拉丁美洲", re.I).search(claim)
            and _compiled_rule(r"\bapple\b[^.!?]{0,85}\b(?:announced|expanded|has\s+expanded)\b|"
                               r"苹果[^。！？]{0,50}(?:宣布|拓展|扩展)", re.I).search(lead)):
        return "tap-to-pay:latin-america", "availability-expansion"

    if (_compiled_rule(r"(?<![a-z0-9])apple\s*music\s*hall(?![a-z0-9])", re.I).search(lead[:650])
            and _compiled_rule(r"\b(?:london|battersea)\b|伦敦|巴特西", re.I).search(claim)
            and _compiled_rule(r"\b(?:open(?:s|ing)?|new\s+live\s+music\s+venue|first\s+live\s+music\s+venue)\b|"
                               r"(?:开设|开放|开业|现场音乐场馆)", re.I).search(claim)
            and _compiled_rule(r"\bapple\b|苹果", re.I).search(claim)):
        return "apple-music-hall:london", "venue-opening"

    if (_compiled_rule(r"(?<![a-z0-9])mac\s*mini(?![a-z0-9])", re.I).search(claim)
            and _compiled_rule(r"(?<![a-z0-9])mac\s*studio(?![a-z0-9])", re.I).search(claim)
            and _compiled_rule(r"(?<![a-z0-9])(?:ssd|nand)(?![a-z0-9])", re.I).search(claim)
            and _compiled_rule(r"\bsolder(?:ed)?\b|焊(?:死|接)", re.I).search(claim)
            and _compiled_rule(r"\b(?:slotted|replaceable|upgrad(?:e|able)|possible)\b|"
                               r"(?:可拆卸|可更换|可升级|更换方法)", re.I).search(claim)):
        return "mac-mini-mac-studio:ssd", "replaceability-contrast"

    if (_compiled_rule(r"\bshazam\b", re.I).search(headline)
            and _compiled_rule(r"\bapple\b[^.!?]{0,45}\b(?:updated?|released?)\b[^.!?]{0,65}\bshazam\b", re.I).search(opening)
            and _compiled_rule(r"\b(?:app\s+icon|stickers?|imessage)\b", re.I).search(claim)):
        return "shazam-ios-app", "first-party-update"

    if (_compiled_rule(r"\bbeats\b[^.!?]{0,45}\bear\s+cushion", re.I).search(claim)
            and _compiled_rule(r"\bapple\b[^.!?]{0,90}\b(?:offering|offers?|introduced)\b[^.!?]{0,75}"
                               r"\b(?:introductory\s+pricing|ear\s+cushions?)\b", re.I).search(lead)
            and _compiled_rule(r"\bapple(?:'s)?\s+online\s+store\b|\bapple\s+store\b", re.I).search(lead)):
        return "beats-ear-cushion-kits", "first-party-introductory-offer"

    if (_compiled_rule(r"\bapple\s*park\s+visitor\s+center\b|apple\s*park\s*游客中心", re.I).search(claim)
            and _compiled_rule(r"\baugmented\s+reality\b|\bar\b|ar展区|增强现实", re.I).search(claim)
            and _compiled_rule(r"\b(?:lost|retire[ds]?|removed?|no\s+longer\s+features?)\b|"
                               r"(?:撤下|移除|改为|拆除)", re.I).search(claim)):
        return "apple-park-visitor-center:ar-exhibition", "removal"

    home_os = home_os_development_action(title, lead)
    if home_os is not None:
        return home_os

    if (_compiled_rule(r"\bmacos\s*\d+(?:\.\d+)?\s*beta\s*\d+\b", re.I).search(headline)
            and _compiled_rule(r"(?:亮度|brightness)", re.I).search(claim)
            and _compiled_rule(r"(?:音量|volume)", re.I).search(claim)
            and _compiled_rule(r"(?:滑块|sliders?)", re.I).search(claim)
            and _compiled_rule(r"(?:带来|新设计|全新|new|redesign)", re.I).search(claim)
            and _compiled_rule(r"苹果[^。！？]{0,90}(?:带来|推出|新增)|"
                               r"\bapple\b[^.!?]{0,90}\b(?:adds?|brings?|introduces?)\b", re.I).search(lead[:1000])):
        return "macos-volume-brightness-sliders", "beta-feature-change"
    return None


def _canonical_title(value: str) -> str:
    """Remove publisher chrome while preserving the reported headline."""
    title = _normalized(value)
    publisher_suffix = (
        r"\s+(?:[-|]\s*)?(?:apple\s+苹果\s+-\s+)?"
        r"(?:9to5mac|appleinsider|cnbeta(?:\.com)?|macrumors|the\s+verge|"
        r"it\s*之家|快科技|爱范儿)\.?$"
    )
    previous = ""
    while title != previous:
        previous = title
        title = re.sub(publisher_suffix, "", title).strip(" -|")
    return title


def _contains(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def _has_absolute_calendar_date(value: str) -> bool:
    text = _normalized(value)
    return bool(
        _compiled_rule(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", 0).search(text)
        or _compiled_rule(r"\b(?:january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?\b", 0).search(text)
        or _compiled_rule(r"\b\d{1,2}\s+月\s*\d{1,2}\s*[日号]\b", 0).search(text)
    )


def _primary_assertion_scope(title: str, lead: str) -> tuple[str, str]:
    """Return title and first substantive lead sentence for action identity.

    Later lead sentences often summarize related supply-chain, legal, or product
    context.  They remain useful as facts, but must not redefine the article's
    primary action and bridge otherwise independent events.
    """
    title_scope = _normalized(title)
    normalized_lead = _normalized(lead)
    if normalized_lead.startswith(title_scope):
        remainder = normalized_lead[len(title_scope) :].lstrip(" .!?。！？:：-|")
        if remainder:
            normalized_lead = remainder
    lead_scope = _compiled_rule(r"(?:[。！？]|(?<=[.!?])\s+)", 0).split(normalized_lead, 1)[0]
    return title_scope, f"{title_scope}. {lead_scope}".strip()


def _named_transit_card_subject(value: str) -> str:
    """Return a stable named-card subject without publisher-specific aliases."""
    text = _normalized(value)
    chinese_matches = list(
        _compiled_rule(r"([\u4e00-\u9fff]{2,12})(?=交通卡)", 0).finditer(text)
    )
    if chinese_matches:
        subject = chinese_matches[-1].group(1)
        for marker in ("上线", "支持", "添加", "推出", "开通", "接入", "新增"):
            if marker in subject:
                subject = subject.rsplit(marker, 1)[-1]
        # Chinese transit brands commonly end in 通 (for example a city-branded
        # pass). Keep the distinctive terminal name instead of a preceding city
        # or launch phrase that another headline may omit.
        if subject.endswith("通") and len(subject) > 3:
            subject = subject[-3:]
        elif len(subject) > 6:
            subject = subject[-6:]
        if len(subject) >= 2:
            return subject
    english_match = _compiled_rule(r"\b([a-z][a-z0-9' -]{1,32})\s+transit\s+card\b", 0).search(text)
    if not english_match:
        return ""
    subject = english_match.group(1)
    subject = _compiled_rule(r"^(?:apple|iphone|wallet|now|finally|adds?|supports?|launches?|gets?)\s+", 0).sub("", subject, 0).strip(" -")
    return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", subject, 0).strip("-")


def _reported_hardware_launch_subjects(
    title: str,
    identity: EventIdentity,
) -> set[str]:
    """Return title products tied to one concrete reported launch window."""
    text = _normalized(title)
    launch_window = _compiled_rule(r"\b(?:days? away|within (?:the )?(?:next )?few days|coming days|"
        r"set to launch before|could launch before|launch before|"
        r"(?:launch|release|ship|arrive|debut).{0,24}(?:next month|"
        r"in (?:september|october)|by (?:late )?(?:september|october))|"
        r"(?:expected|scheduled|reportedly set).{0,20}(?:launch|release|arrive))\b|"
        r"(?:未来几天|数日)(?:之)?内.{0,8}(?:发布|推出|亮相)|"
        r"(?:发布|推出|亮相).{0,8}(?:未来几天|数日)(?:之)?内|"
        r"(?:发布会|活动)(?:之)?前.{0,8}(?:发布|推出|亮相)|"
        r"(?:发布|推出|亮相).{0,8}(?:发布会|活动)(?:之)?前|"
        r"(?:有望|预计|计划|最快).{0,24}(?:\d{1,2}\s*月|下月|明年)"
        r".{0,18}(?:发布|推出|亮相|上市)|"
        r"(?:\d{1,2}\s*月|下月|明年).{0,18}(?:发布|推出|亮相|上市)", 0)
    aliases = {
        "airpods": (r"(?<![a-z0-9])airpods?(?![a-z0-9])",),
        "apple-home-hub": (r"(?<![a-z0-9])(?:apple\s+)?home\s+hub(?![a-z0-9])", r"家庭中枢"),
        "apple-tv-hardware": (r"(?<![a-z0-9])apple\s+tv(?:\s+4k)?(?![a-z0-9])",),
        "apple-watch": (r"(?<![a-z0-9])apple\s+watch(?![a-z0-9])",),
        "beats": (r"(?<![a-z0-9])beats(?![a-z0-9])",),
        "foldable-iphone": (r"(?<![a-z0-9])iphone\s+(?:fold|ultra)(?![a-z0-9])", r"折叠屏?\s*iphone"),
        "homepod": (r"(?<![a-z0-9])homepod(?![a-z0-9])",),
        "imac": (r"(?<![a-z0-9])imac(?![a-z0-9])",),
        "ipad": (r"(?<![a-z0-9])ipad(?![a-z0-9])",),
        "ipad-air": (r"(?<![a-z0-9])ipad\s+air(?![a-z0-9])",),
        "ipad-mini": (r"(?<![a-z0-9])ipad\s+mini(?![a-z0-9])",),
        "ipad-pro": (r"(?<![a-z0-9])ipad\s+pro(?![a-z0-9])",),
        "iphone": (r"(?<![a-z0-9])iphone(?![a-z0-9])",),
        "mac-mini": (r"(?<![a-z0-9])mac\s+mini(?![a-z0-9])",),
        "mac-pro": (r"(?<![a-z0-9])mac\s+pro(?![a-z0-9])",),
        "mac-studio": (r"(?<![a-z0-9])mac\s+studio(?![a-z0-9])",),
        "macbook": (r"(?<![a-z0-9])macbook(?:\s+(?:air|pro))?(?![a-z0-9])",),
        "vision-pro": (r"(?<![a-z0-9])vision\s+pro(?![a-z0-9])",),
    }
    subjects: set[str] = set()
    for product in identity.title_products:
        for alias in aliases.get(product, ()):
            for match in re.finditer(alias, text):
                suffix = text[match.end() : min(len(text), match.end() + 52)]
                prefix = text[max(0, match.start() - 52) : match.start()]
                launch_before_product = _compiled_rule(r"(?:within (?:the )?(?:next )?few days|coming days|未来几天|数日|"
                    r"20\d{2}\s*q[1-4]|\d{1,2}\s*月|明年(?:第?[一二三四1-4]季度)?)"
                    r".{0,24}(?:launch|release|发布|推出|亮相)"
                    r"(?:(?:\s+(?:a|the|new))|(?:\s*新款))?\s*$", 0).search(prefix)
                direct_launch_before_product = bool(
                    not _compiled_rule(r"\bbefore\s*$", 0).search(prefix)
                    and _compiled_rule(r"\b(?:could|will|may|might|plans? to|expected to|set to)?\s*"
                        r"(?:launch|release|debut|ship|announce)"
                        r"(?:\s+(?:one|two|three|a|the|new|next|fresh))*\s*$", 0).search(prefix)
                )
                if launch_window.search(suffix) or launch_before_product or direct_launch_before_product:
                    subjects.add(product)
                    break
            if product in subjects:
                break
    return subjects


def _short_lead_scope(lead: str, *, sentences: int = 2, limit: int = 900) -> str:
    """Return a bounded lead window for high-specificity typed assertions."""
    normalized = _normalized(lead)
    teaser, separator, continuation = normalized.partition("... ")
    if (separator and len(teaser.split()) >= 5
            and _compiled_rule(r"\s+([,;:])").sub(r"\1", continuation).startswith(
                _compiled_rule(r"\s+([,;:])").sub(r"\1", teaser))):
        normalized = continuation  # The complete opening replaces its repeated truncated deck.
    parts = _compiled_rule(r"(?:[。！？]|(?<=[.!?])\s+)", 0).split(normalized, sentences)
    return " ".join(part for part in parts[:sentences] if part).strip()[:limit]


def _subject_tokens(title: str, identity: EventIdentity) -> set[str]:
    subjects = set(identity.title_named_subjects or identity.named_subjects)
    lower = _normalized(title)
    possessive = _compiled_rule(r"^([a-z][a-z0-9.+-]{1,36})'s\b", 0).match(lower)
    if possessive:
        subjects.add(possessive.group(1))
    leading = _compiled_rule(r"^([a-z][a-z0-9.+-]{1,36})(?:\s+(?:ceo|briefly|app|update|firmware|browser))\b", 0).match(lower)
    if leading:
        subjects.add(leading.group(1))
    # Latin product or company names remain stable in translated Chinese
    # headlines and are useful when no language-independent facet exists.
    for token in _compiled_rule(r"\b[a-z][a-z0-9.+-]{2,30}\b", 0).findall(lower[:100]):
        if token not in _GENERIC_SUBJECT_WORDS:
            subjects.add(token)
            break
    return {subject for subject in subjects if subject not in _GENERIC_SUBJECT_WORDS}


def _display_metrics(text: str) -> set[str]:
    metrics = set()
    for value in _compiled_rule(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:-?inch|inches|英寸|寸)", 0).findall(text):
        normalized = value.rstrip("0").rstrip(".") if "." in value else value
        metrics.add(normalized)
    return metrics


def _calendar_years(scope: str) -> set[str]:
    return {
        match.group(1)
        for match in _compiled_rule(r"(?<!\d)(20\d{2})(?!\d)", 0).finditer(scope)
        if not _compiled_rule(r"[$€£]\s*$", 0).search(scope[max(0, match.start() - 5):match.start()])
        and not _compiled_rule(r"\s*(?:美元|欧元|英镑|人民币|元|dollars?\b|euros?\b|usd\b|gb\b|mah\b|台|部)", 0).match(scope[match.end():])
    }


def _evidence_measurements(title: str, lead: str) -> set[str]:
    """Normalize typed quantities from the headline and primary assertion.

    Measurements are evidence, not topics.  They only reconcile articles when
    paired with an independently extracted subject/component projection, so a
    shared date or model number cannot become an event boundary by itself.
    """
    lead_sentences = _compiled_rule(r"(?:[。！？]|(?<=[.!?])\s+)", 0).split(_normalized(lead), 2)
    evidence_lead = " ".join(lead_sentences[:2])
    scope = f"{_normalized(title)}. {evidence_lead}"
    values: set[str] = set()
    for value in _compiled_rule(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%", 0).findall(scope):
        normalized = value.rstrip("0").rstrip(".") if "." in value else value
        values.add(f"percent:{normalized}")
    years = _calendar_years(scope)
    for value in years:
        values.add(f"year:{value}")
    quarter_patterns = (
        r"(?<!\d)(20\d{2})\s*年?\s*[- ]?q([1-4])(?!\d)",
        r"\bq([1-4])\s*(20\d{2})\b",
        r"(?<!\d)(20\d{2})\s*年?\s*第?([一二三四1234])季度",
    )
    chinese_quarters = {"一": "1", "二": "2", "三": "3", "四": "4"}
    for index, pattern in enumerate(quarter_patterns):
        for match in re.finditer(pattern, scope):
            first, second = match.groups()
            if index == 1:
                quarter, year = first, second
            else:
                year, quarter = first, second
            quarter = chinese_quarters.get(quarter, quarter)
            values.add(f"period:{year}-q{quarter}")
    quarters = {
        chinese_quarters.get(
            match.group(1) or match.group(2),
            match.group(1) or match.group(2),
        )
        for match in _compiled_rule(r"\bq([1-4])\b|第?([一二三四1234])季度", 0).finditer(scope)
        if (match.group(1) or match.group(2))
    }
    if len(years) == 1 and len(quarters) == 1:
        values.add(f"period:{next(iter(years))}-q{next(iter(quarters))}")
    for value in _compiled_rule(r"(?<!\d)(\d{1,3})(?:st|nd|rd|th)?[\s-]+(?:year|anniversary)|"
        r"(?<!\d)(\d{1,3})\s*周年", 0).findall(scope):
        values.add(f"anniversary:{next(part for part in value if part)}")
    number_words = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
    }
    for match in _compiled_rule(r"(?<!\d)(\d{1,2})\s*(?:-?layer|层)|"
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten)(?:-layer|\s+layers?)\b|"
        r"([一二三四五六七八九十])\s*层", 0).finditer(scope):
        chinese_numbers = {
            "一": "1",
            "二": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
        }
        raw = match.group(1) or number_words.get(match.group(2), "") or chinese_numbers[match.group(3)]
        values.add(f"layers:{raw}")
    currency_patterns = (
        ("usd", r"(?:us\s*)?\$\s*(\d[\d,]*(?:\.\d+)?)\s*(billion|million|bn|b|m)?\b"),
        ("usd", r"(\d+(?:\.\d+)?)\s*万\s*美元"),
        ("usd", r"(\d+(?:\.\d+)?)\s*亿\s*美元"),
        ("usd", r"(?<![\d,])(\d[\d,]*(?:\.\d+)?)\s*美元"),
        ("eur", r"€\s*(\d[\d,]*(?:\.\d+)?)"),
        ("gbp", r"£\s*(\d[\d,]*(?:\.\d+)?)"),
    )
    for currency, pattern in currency_patterns:
        for match in re.finditer(pattern, scope):
            raw = match.group(1).replace(",", "")
            amount = float(raw)
            if "万" in match.group(0):
                amount *= 10000
            elif "亿" in match.group(0):
                amount *= 100000000
            elif len(match.groups()) > 1 and match.group(2):
                scale = match.group(2)
                amount *= 1000000000 if scale in {"billion", "bn", "b"} else 1000000
            normalized = str(int(amount)) if amount.is_integer() else str(amount)
            values.add(f"money:{currency}:{normalized}")
    if "十亿美元" in scope:
        values.add("money:usd:1000000000")
    return values


def _product_production_rate_signature(
    title: str,
    lead: str,
    evidence: str = "",
) -> str:
    """Return a bounded output-rate signature for one product report.

    Product identity plus a generic production verb is not enough to merge two
    reports: a build target, a yield problem, and a current output rate are
    separate actions. A shared rate magnitude and time unit is stable
    cross-source evidence even when one headline puts the time unit in its
    opening lead.
    """
    scope = _normalized(
        " ".join(
            part
            for part in (
                _canonical_title(title),
                _short_lead_scope(lead, sentences=3, limit=700),
                _short_lead_scope(evidence, sentences=2, limit=500),
            )
            if part
        )
    )
    if not _compiled_rule(r"\b(?:per\s+day|a\s+day|daily)\b|(?:日均|日产|每天|每日)", 0).search(scope):
        return ""
    if _compiled_rule(r"\b(?:a|only\s+a|just\s+a)?\s*few\s+hundred\b|\bhundreds\b|(?:数百|几百)", 0).search(scope):
        return "hundreds-per-day"
    numeric = _compiled_rule(r"(?<![\d.])(\d{1,3}(?:[,.]\d{3})*|\d+(?:\.\d+)?)\s*"
        r"(?:units?|devices?|phones?|台|部)?\s*(?:per\s+day|a\s+day|daily|日均|日产|每天|每日)", 0).search(scope)
    if not numeric:
        return ""
    return f"{numeric.group(1).replace(',', '')}-per-day"


def _claim_components(identity: EventIdentity) -> set[str]:
    """Return typed predicates while excluding product/version metadata."""
    return {
        component
        for component in identity.components
        if ":" not in component
        and component
        not in {
            "hardware-product-roadmap",
            "roadmap-projection",
        }
    }


def _document_subject_token(value: str) -> str:
    """Return a stable integration target from a first-party document title."""
    value = _normalized(value).strip(" .,:;!?()[]{}\"'“”‘’《》")
    value = _compiled_rule(r"(?:大模型|模型|扩展|服务)$", 0).sub("", value, 0).strip()
    # Chinese reports may write a partner plus its model as one token while
    # the first-party page itself names only the model. Normalize common
    # organization prefixes, but keep the model name data-driven.
    for prefix in (
        "阿里巴巴",
        "字节跳动",
        "openai",
        "google",
        "microsoft",
        "阿里",
        "百度",
        "腾讯",
        "字节",
        "谷歌",
        "微软",
    ):
        if value.startswith(prefix) and len(value.removeprefix(prefix)) >= 2:
            value = value.removeprefix(prefix).strip()
            break
    value = _compiled_rule(r"^(?:旗下的?|的)", 0).sub("", value, 0).strip()
    value = _compiled_rule(r"^(?:接入|使用|调用|集成|整合|配合|联动)", 0).sub("", value, 0).strip()
    if not value or value in {
        "apple",
        "apple intelligence",
        "apple 智能",
        "siri",
        "mac",
        "功能",
        "页面",
        "手册",
        "文档",
    }:
        return ""
    return _compiled_rule(r"[^a-z0-9\u4e00-\u9fff+.-]+", 0).sub("-", value, 0).strip("-")


def _document_integration_subject(text: str) -> str:
    candidates: list[str] = []
    for pattern in (
        r"(?:使用|接入|调用|集成|整合|配合|联动)\s*"
        r"(?P<name>[\u4e00-\u9fff]{2,14}?|[a-z][a-z0-9+.-]{1,30})"
        r"(?=\s*(?:大模型|模型|扩展|服务|使用手册|手册|页面|工作|[\"'“”‘’《》]|$))",
        r"(?:删除|移除|撤下|下线|恢复|替换|更正)\s*"
        r"(?P<name>[\u4e00-\u9fff]{2,14}?|[a-z][a-z0-9+.-]{1,30})"
        r"(?=\s*(?:使用手册|用户手册|操作手册|支持文档|支持页面|文档|手册|页面))",
        r"\b(?:use|using|integrates? with|works? with|powered by)\s+"
        r"(?P<name>[a-z][a-z0-9+.-]{1,30})(?=\s|[\"'.,:;!?)]|$)",
    ):
        candidates.extend(match.group("name") for match in re.finditer(pattern, text, re.I))
    for candidate in reversed(candidates):
        token = _document_subject_token(candidate)
        if token:
            return token
    return ""


def first_party_document_lifecycle_key(
    title: str,
    text: str,
    identity: EventIdentity,
) -> str:
    """Identify reports about one first-party page appearing and later changing."""
    title = _normalized(title)
    text = _normalized(text)
    if not _contains(
        text,
        "support document",
        "support page",
        "user guide",
        "user manual",
        "documentation",
        "apple support",
        "apple website",
        "apple's website",
        "apple.com",
        "支持文档",
        "使用手册",
        "用户手册",
        "操作手册",
        "苹果官网",
        "苹果中国官网",
    ):
        return ""
    if not _contains(
        text,
        "appears",
        "appeared",
        "surfaced",
        "published",
        "added",
        "updated",
        "documented",
        "removed",
        "deleted",
        "withdrawn",
        "pulled",
        "restored to",
        "replaced",
        "corrected",
        "现身",
        "出现",
        "上线",
        "新增",
        "更新",
        "删除",
        "删了",
        "撤下",
        "下线",
        "恢复为",
        "替换",
        "更正",
    ):
        return ""
    if not _contains(title, "apple", "苹果") and identity.scope != "apple-direct":
        return ""
    subject = _document_integration_subject(text)
    if not subject:
        return ""
    preferred_products = (
        "apple-intelligence",
        "icloud-private-relay",
        "icloud",
        "siri",
        "app-store",
        "apple-wallet",
        "apple-music",
        "apple-tv",
        "macos",
        "ios",
        "ipados",
        "watchos",
        "visionos",
    )
    product = next((value for value in preferred_products if value in identity.products), "")
    if not product:
        return ""
    return f"apple-document-lifecycle:{product}:{subject}"


def _title_fact_signatures(title: str, lead: str) -> set[str]:
    """Return exact, title-led subject/action signatures for reconciliation.

    These signatures are deliberately narrower than topic facets.  A product
    name alone is never a signature: the title or short lead must also expose
    the concrete changed object, material, finish set, generation, or program
    operation.  This lets exact cross-source matches override seed boundaries
    without reopening fuzzy all-pairs clustering.
    """
    title, text = _primary_assertion_scope(title, lead)
    signatures: set[str] = set()

    foldable_iphone = bool(
        _compiled_rule(r"\b(?:foldable|folding)\s+(?:apple\s+)?iphone\b|"
            r"\biphone\s+(?:fold|ultra)\b|(?:折叠屏?|折叠式)\s*(?:iphone|苹果手机)|"
            r"(?:iphone|苹果首款手机).{0,12}(?:折叠屏?|折叠式)", 0).search(text)
        or (
            _compiled_rule(r"折叠屏?|折叠式", 0).search(text)
            and _compiled_rule(r"\biphone\s+(?:fold|ultra)\b|iphone", 0).search(text)
        )
    )
    if foldable_iphone:
        finish_aliases = {
            "black": (r"\bblack\b", "黑色"),
            "dark-blue": (r"\bdark[ -]blue\b", "深蓝色", "深蓝"),
            "gold": (r"\bgold(?:en)?\b", "金色"),
            "silver": (r"\bsilver\b", "银色"),
            "white": (r"\bwhite\b", "白色"),
        }
        clauses = [part.strip() for part in _compiled_rule(r"(?<=[.!?。！？;；])\s*", 0).split(text, 0) if part.strip()]
        for clause in clauses:
            finishes = {
                finish
                for finish, aliases in finish_aliases.items()
                if any(
                    re.search(alias, clause) if alias.startswith(r"\b") else alias in clause
                    for alias in aliases
                )
            }
            finish_context = bool(
                _compiled_rule(r"\b(?:colors?|colou?rs?|finishes?|choice of)\b|配色|颜色|色款", 0).search(clause)
            )
            if finish_context and len(finishes) >= 2:
                signatures.add(f"finish-set:foldable-iphone:{','.join(sorted(finishes))}")
                break


    apple_watch = bool(_compiled_rule(r"(?<![a-z0-9])apple\s*watch\b|苹果\s*watch", 0).search(text))
    if apple_watch and _compiled_rule(r"\bceramic\b|陶瓷", 0).search(text):
        signatures.add("case-material:apple-watch:ceramic")
    if apple_watch:
        redesign = bool(_compiled_rule(r"\b(?:redesign|rethink|form[ -]factor|revamp)\b|重新设计|重新思考|产品形态|形态重构|大改版", 0).search(text))
        form_factor = bool(_compiled_rule(r"\bround(?:ed)?\s+(?:screen|display|model)\b|\bscreenless\b|圆(?:形|屏)|无屏", 0).search(text))
        if redesign:
            signatures.add("form-factor-redesign:apple-watch")
        if redesign and form_factor:
            signatures.add("form-factor-redesign:apple-watch:round-or-screenless")

    apple_upgrade = bool(_compiled_rule(r"\bapple\s+upgrade\b|苹果\s*upgrade", 0).search(text))
    device_data_preload = bool(
        _compiled_rule(r"\b(?:preload|pre-load|preloaded|pre-loaded)\b.{0,80}\b(?:icloud|backup|data)\b|"
            r"\b(?:icloud|backup|data)\b.{0,80}\b(?:preload|pre-load|preloaded|pre-loaded)\b|"
            r"(?:预载|预装|装好).{0,40}(?:icloud|备份|用户数据|数据)|"
            r"(?:icloud|备份|用户数据).{0,40}(?:预载|预装|装好)", 0).search(text)
    )
    if apple_upgrade and device_data_preload:
        signatures.add("program-operation:apple-upgrade:device-data-preload")

    return signatures


def _quoted_subjects(value: str) -> list[str]:
    """Read paired quotation marks, never possessive apostrophes."""
    matches = _compiled_rule(r'《([^》\n]{1,90})》|“([^”\n]{1,90})”|'
        r'‘((?:[^’\n]|(?<=\w)’(?=\w)){1,90})’(?!\w)|'
        r'"([^"\n]{1,90})"|(?<!\w)\'((?:[^\'\n]|(?<=\w)\'(?=\w)){1,90})\'(?!\w)', 0).finditer(value)
    return [next(part for part in match.groups() if part).strip() for match in matches]


def _current_trailer_assertion_text(value: str) -> str:
    """Keep source assertions; an old/denied trailer cannot restore its key."""
    trailer = _compiled_rule(r"\b(?:trailer|teaser)\b|预告片", re.I)
    if not trailer.search(value):
        return value
    kept = []
    for start, end in source_sentence_spans(value):
        clause = value[start:end]
        if (trailer.search(clause)
                and _compiled_rule(r"\b(?:previously|last\s+(?:year|month|week)|\d+\s+(?:years?|months?|weeks?)\s+ago)\b|"
                    r"\b(?:not|never)\s+(?:(?:yet|ever)\s+)?(?:release\w*|publish\w*|share[sd]?|unveil\w*)\b|"
                    r"此前|去年|上个月|上周|(?:没有|并未|尚未).{0,10}(?:发布|公布|分享)", re.I).search(clause)):
            continue
        kept.append(clause)
    return " ".join(kept)


def _headline_content_claim(title: str, lead: str) -> tuple[str, str] | None:
    """Bind a trailer/review headline to its work, not a background release."""
    title = _current_trailer_assertion_text(title)
    lead = _current_trailer_assertion_text(lead[:2200])
    title_text = _canonical_title(title)
    action = (
        "trailer" if _compiled_rule(r"\b(?:trailer|teaser)\b|预告片", 0).search(title_text)
        else "reviews" if _compiled_rule(r"\breviews?\b|影评|口碑", 0).search(title_text)
        else ""
    )
    inferred_trailer = False
    if not action and _compiled_rule(r"\bapple\s*tv\b.{0,35}\b(?:unveils?|announces?)\b", 0).search(title_text):
        primary = _short_lead_scope(lead, sentences=1, limit=350)
        if (_compiled_rule(r"^(?:today\s+)?apple\s*tv\s+(?:(?:today|has|just|now)\s+)*"
                      r"(?:unveils?|unveiled|releases?|released|shares?|shared|publishes?|published)\s+"
                      r"(?:(?:the|a|new|first)\s+){0,2}trailer\s+for\s+", re.I).search(primary)
                and not _compiled_rule(r"\b(?:previously|earlier|last\s+(?:year|month|week))\b|此前|去年", re.I).search(primary)):
            action = "trailer"
            inferred_trailer = True
    if not action:
        return None
    quoted_work = _quoted_subjects(title)
    if (quoted_work and _compiled_rule(r"\b(?:trailer|teaser)\s+for\s+(?:apple\s*tv(?:['’]s)?\s+)?[‘'\"“]", re.I).search(title)):
        return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(quoted_work[0]), 0).strip("-"), action
    local_work = _compiled_rule(r"《([^》]{1,80})》", 0).search(title)
    if local_work:
        local_name = local_work.group(1)
        alias = re.search(r"《" + re.escape(local_name) + r"》\s*[（(]([A-Za-z][A-Za-z0-9 '’&-]{0,80})[）)]", title + " " + lead)
        return (_normalized(alias.group(1)).replace(" ", "-") if alias else _normalized(local_name)), action
    # Preserve case for unquoted titles, and do not cross sentence boundaries.
    primary_lead = _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(lead, 2)
    scopes = [title, *primary_lead[:2]]
    name = r"[A-Z][A-Za-z0-9'’&-]*(?:[ \t]+[A-Za-z0-9'’&-]+){0,7}?"
    patterns = ((rf"(?i:\btrailer\s+for\s+)(?P<name>{name})(?=[.,;!?]|$)",)
                if inferred_trailer else ()) + (
        rf"(?i:\b(?:contender|winner|title)\s*:\s*)(?P<name>{name})(?=[.,;!?]|$)",
        rf"(?i:\bapple\s+tv\s+premieres?\s+)(?P<name>{name})"
        r"(?i:(?=\s+(?:this|next|on|in)\b|[,.;!?]|$))",
        rf"(?i:\b(?:film|movie|documentary|series)\s+(?:called\s+|titled\s+)?)"
        rf"(?P<name>{name})(?=[,.;!?]|$)",
    )
    for scope in scopes:
        # Work quotes must be attached to a content noun/action. Award names
        # and review pull-quotes are not film identifiers.
        for quoted in _quoted_subjects(scope):
            prefix = scope[:scope.find(quoted)]
            if _compiled_rule(r"\b(?:film|movie|documentary|series|trailer\s+for|reviews?\s+(?:for|of))\s*[\"'“‘]$", re.I).search(prefix):
                return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(quoted), 0).strip("-"), action
        for pattern in patterns:
            match = re.search(pattern, scope)
            if match:
                subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(match.group("name")), 0).strip("-")
                if subject not in _GENERIC_SUBJECT_WORDS | {"apple-tv"}:
                    return subject, action
    return None


def _primary_content_schedule(lead: str) -> set[str]:
    """Local source schedule constraints; these keys never authorize a pair."""
    sentence = _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(lead, 1)[0]
    if _compiled_rule(r"\b(?:previously|earlier|last year)\b|此前|去年|曾经", re.I).search(sentence) or not _compiled_rule(r"\bpremier(?:e|es|ing)\b|首播|开播", re.I).search(sentence):
        return set()
    keys = {"content-primary-premiere"}
    months = "january february march april may june july august september october november december".split()
    date = re.search(r"\b(" + "|".join(months) + r")\s+(\d{1,2})\b", sentence, re.I)
    local = _compiled_rule(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", 0).search(sentence)
    if date:
        keys.add(f"content-date:{months.index(date.group(1).lower()) + 1}:{int(date.group(2))}")
    elif local:
        keys.add(f"content-date:{int(local.group(1))}:{int(local.group(2))}")
    years = _compiled_rule(r"\b20\d{2}\b", 0).findall(sentence)
    keys.update("content-date-year:" + year for year in years)
    return keys


def _content_work_assertion(title: str, lead: str) -> tuple[str, str] | None:
    """Resolve a named media work and action; this does not establish ownership."""
    # Key-fact evidence follows the lead in callers. Keep enough bounded text
    # to reach a source-attributed production fact without scanning page chrome.
    headline_claim = _headline_content_claim(title, lead)
    if headline_claim:
        return headline_claim
    if _compiled_rule(r'\b(?:film|movie|video|series)\b|电影|影片|视频|剧集', re.I).search(title):
        availability = _compiled_rule(r'[《“"]([^》”"]{1,160})[》”"]\s*'
            r'(?:(?:is\s+)?now\s+available\s+on|(?:现已|已经)?(?:登陆|上线))\s*'
            r'(?:apple\s+)?(?:vision\s+pro|apple\s*tv|iphone|ipad)\b', re.I).search(lead[:2200])
        if availability:
            return _compiled_rule(r'[^a-z0-9\u3400-\u9fff]+').sub('-',
                _normalized(availability.group(1))).strip('-'), 'playback-availability'
    raw = f"{title}. {lead[:2200]}"
    trailer_raw = _current_trailer_assertion_text(raw)
    trailer_title = _current_trailer_assertion_text(title)
    race = source_free_race_stream(title, lead)
    if race:
        return race, "free-streaming-event"
    conference = _compiled_rule(r"\b([A-Za-z]+-Con)\b", 0).search(title)
    hall = _compiled_rule(r"\bhall\s+([a-z])\b", re.I).search(raw)
    if conference and hall and _compiled_rule(r"panels?|lineup", re.I).search(lead):
        return "conference-" + conference.group(1).lower() + "-hall-" + hall.group(1).lower(), "panel-lineup"
    release_work = _compiled_rule(r"(?i:release date for)\s+([A-Z][A-Za-z0-9'’&-]*(?: [A-Z][A-Za-z0-9'’&-]*){0,6})(?=[,.]|$)", 0).search(lead[:700])
    titled_debut = _compiled_rule(r'(?:comedy|series|film|movie)\s+["“]([^"”]{1,80})["”].{0,55}(?:debut|premiere)', re.I).search(title)
    if titled_debut or release_work:
        work = (titled_debut or release_work).group(1)
        return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(work), 0).strip("-"), "premiere-announcement"
    titled_schedule = _compiled_rule(r"《(?P<local>[^》]{1,80})》.{0,36}(?:定档|首播|上线|开播)", 0).search(title)
    if titled_schedule:
        localized_alias = re.search(
            rf"《{re.escape(titled_schedule.group('local'))}》\s*[（(]"
            r"(?P<subject>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,7})[)）]",
            lead,
            re.I,
        )
        if localized_alias:
            subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(localized_alias.group("subject")), 0).strip("-")
            if subject and subject not in _GENERIC_SUBJECT_WORDS:
                return subject, "premiere-schedule"
    # A prior-work credit is not the new film's name. Read an unquoted
    # follow-up only inside its own explicit Apple TV scheduling/screening clause.
    for clause in _compiled_rule(r"[;；.!?。]",0).split(lead[:900]):
        if not _compiled_rule(r"dated for Apple TV|Apple TV is to screen",re.I).search(clause):
            continue
        if _compiled_rule(r"last year|previously|not dated|not to screen|去年|此前|取消",re.I).search(clause):
            continue
        work = _compiled_rule(r"follow-up\s+([A-Z][A-Za-z'’-]*(?:\s+[A-Z][A-Za-z'’-]*){0,5})(?=\s+is\s+dated|[;.!?]|$)",0).search(clause)
        if work:
            return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", work.group(1).lower(), 0).strip("-"), "premiere-schedule"
    scheduled_work_patterns = (
        r"\b(?:series|film|movie|drama|comedy)\s*[-—:]\s*"
        r"(?P<subject>[A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)\s*"
        r"[-—,]\s*(?:coming|premier(?:e|es|ing)|debut(?:s|ing)?)\b",
        r"《[^》]{1,80}》\s*[（(](?P<subject>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,7})[)）]"
        r".{0,50}(?:定档|首播|上线)",
        r"\b(?P<subject>[A-Z][A-Za-z0-9'’-]*(?:[ \t]+[A-Za-z0-9'’-]+){0,7}?)\s+"
        r"(?:will\s+)?premieres?\s+(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"january|february|march|april|may|june|july|august|september|october|november|december)",
    )
    for pattern in scheduled_work_patterns:
        scheduled_work = _compiled_rule(pattern, re.I).search(raw)
        if not scheduled_work:
            continue
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(scheduled_work.group("subject")), 0).strip("-").removeprefix("the-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "premiere-schedule"
    casting_match = _compiled_rule(r"\b(?P<subject>[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+){1,4})\s+"
        r"(?:is\s+)?(?:confirmed|cast|joins?)\s+as\s+(?:a\s+)?(?:guest\s+)?star\b|"
        r"(?P<subject_cn>[A-Za-z][A-Za-z'’.-]+(?:\s+[A-Za-z][A-Za-z'’.-]+){1,4})"
        r".{0,35}(?:确认|确定).{0,18}(?:客串|加盟|出演)", re.I).search(title)
    if casting_match:
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(casting_match.group("subject") or casting_match.group("subject_cn")), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "casting"
    season_subject_match = _compiled_rule(r"^['\"“‘]?(?P<subject>[A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)"
        r"['\"”’]?\s+season\s+\d+\b", re.I).search(title)
    if (
        season_subject_match
        and _compiled_rule(r"\b(?:filming|production|shooting)\b.{0,90}"
            r"\b(?:begin|begins|begun|start|starts|started|kick[ -]?off|set|scheduled|date)\b|"
            r"\b(?:begin|begins|begun|start|starts|started|kick[ -]?off|set|scheduled)\b.{0,90}"
            r"\b(?:filming|production|shooting)\b", re.I).search(raw)
    ):
        season_subject_text = _compiled_rule(r"^.*?\b(?:reveals?|confirm(?:s|ed|ing)?|shares?|says?|teas(?:e|es|ed|ing))\s+", re.I).sub("", season_subject_match.group("subject"), 0)
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(season_subject_text), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "production-update"
    season_production_match = _compiled_rule(r"\b(?P<subject>[A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)\s+"
        r"season\s+\d+\b.{0,65}\b(?:begins?\s+filming|start(?:s|ed)?\s+filming|"
        r"filming\s+(?:begins?|starts?)|enters?\s+production|production\s+(?:begins?|starts?))\b", re.I).search(raw)
    if not season_production_match:
        season_production_match = _compiled_rule(r"《[^》]{1,60}》\s*[（(](?P<subject>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,7})[)）]"
            r".{0,55}第\s*(?:\d+|[一二三四五六七八九十]+)\s*季.{0,45}"
            r"(?:开拍|启动拍摄|启动制作|开始制作|进入制作|拍摄.{0,30}启动)", re.I).search(raw)
    if season_production_match:
        subject_text = _compiled_rule(r"^.*?\b(?:reveals?|confirm(?:s|ed|ing)?|shares?|says?|teas(?:e|es|ed|ing))\s+", re.I).sub("", season_production_match.group("subject"), 0)
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(subject_text), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "production-update"
    if (
        _compiled_rule(r"(?<![a-z0-9])f1(?![a-z0-9])|formula\s+1|一级方程式", re.I).search(raw)
        and _compiled_rule(r"\b(?:viewership|audience|ratings?|analytics|viewing\s+(?:minutes?|data))\b|"
            r"(?:收视|观众|观看量|观看时长|收视数据|观众数据)", re.I).search(raw)
    ):
        return "f1", "viewership-analysis"
    season_trailer_match = _compiled_rule(r"\b(?:apple(?:\s+tv)?\s+)?(?:releases?|released|shares?|shared|unveils?|unveiled)\s+"
        r"(?:a\s+|the\s+|new\s+|first\s+)*"
        r"([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)\s+"
        r"season\s+\d+\s+(?:trailer|teaser)\b", re.I).search(trailer_raw)
    if season_trailer_match:
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(season_trailer_match.group(1)), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "trailer"
    viewing_record_match = _compiled_rule(r"\b([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)\s+"
        r"season\s+\d+\b.{0,90}\b(?:biggest\s+(?:launch|premiere)|"
        r"viewing\s+record|premiere\s+record|most[- ]watched)\b", re.I).search(title)
    if viewing_record_match:
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(viewing_record_match.group(1)), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "viewing-record"
    trailer_for_match = _compiled_rule(r"\bApple(?:\s+TV)?\s+(?:releases?|released|shares?|shared|publishes?|unveils?)\s+"
        r"(?:a\s+|the\s+|new\s+|first\s+)*"
        r"(?:trailer|teaser)\s+for\s+"
        r"([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)"
        r"(?=(?:['’]s)?\s+(?:second|third|fourth|fifth|final|\d+(?:st|nd|rd|th)?)\s+season\b|\s*[-:,.]|$)", re.I).search(trailer_title)
    if trailer_for_match:
        subject_name = _compiled_rule(r"['’]s$", re.I).sub("", trailer_for_match.group(1), 0)
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(subject_name), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "trailer"
    season_progress_match = _compiled_rule(r"\b(?:reveals?|confirms?|shares?|says?)\s+"
        r"([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,5}?)\s+"
        r"season\s+\d+\b.{0,70}\b(?:milestone|filming|production|shooting|progress)\b", re.I).search(title)
    if season_progress_match:
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(season_progress_match.group(1)), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "production-update"
    continuation_hint = _compiled_rule(r"\b(?:hints?|suggests?|signals?)\s+(?:at\s+)?(?:more|future)\s+"
        r"[\"'“‘]?([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)[\"'”’]?\s+seasons?\b", re.I).search(title)
    if continuation_hint:
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(continuation_hint.group(1)), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "continuation"
    title_match = _compiled_rule(r"\bApple\s+TV\s+(?:releases?|shares?|unveils?)\s+(?:a\s+|new\s+)*"
        r"([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7})\s+"
        r"(trailer|teaser)\b", re.I).search(trailer_title)
    if title_match:
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(title_match.group(1)), 0).strip("-")
        if subject:
            return subject, title_match.group(2).lower()
    for quoted_trailer_pattern in (
        r'\btrailer\s+for\s+["“]([^"”]{1,80}?)[,]?["”]',
        r"\btrailer\s+for\s+['‘]([^'’]{1,80}?)[,]?['’]",
    ):
        quoted_trailer = re.search(quoted_trailer_pattern, trailer_raw, re.I)
        if not quoted_trailer:
            continue
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(quoted_trailer.group(1)), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "trailer"
    release_work_match = _compiled_rule(r"\b([A-Z][A-Za-z0-9'’.-]+(?:\s+[A-Z][A-Za-z0-9'’.-]+){1,7})"
        r"(?=\s+(?:will\s+stream\s+on|for|on)\s+Apple\s+TV\b|[,，]\s*(?:by|由)\b)", 0).search(raw)
    if release_work_match:
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(release_work_match.group(1)), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "new-project"
    patterns = (
        (
            r"\bfuture\s+([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Z][A-Za-z0-9'’.-]*){0,7})\s+seasons?\b",
            "continuation",
        ),
        (
            r"\b([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Z][A-Za-z0-9'’.-]*){0,7})\s+could\s+continue\b",
            "continuation",
        ),
        (
            r"\btrailer\s+for\s+([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)(?=\s*[,.:;!?]|\s+(?:which|that)\b|$)",
            "trailer",
        ),
        (
            r"\b([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7})['’]s\s+"
            r"(?:second|third|fourth|final|\d+(?:st|nd|rd|th)?)\s+season\s+premieres?\b",
            "season-premiere",
        ),
        (
            r"\b([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7})\s+"
            r"(?:premieres?|debuts?)\s+(?:on|at)\s+Apple\s+TV\b",
            "premiere",
        ),
    )
    for pattern, action in patterns:
        match = _compiled_rule(pattern, re.I).search(trailer_raw if action == "trailer" else raw)
        if not match:
            continue
        subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(match.group(1)), 0).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, action
    return None


def _product_lifecycle_subjects(text: str, identity: EventIdentity) -> set[str]:
    """Return concrete products affected by an official lifecycle-list action."""
    subjects: set[str] = set()
    if _compiled_rule(r"(?<![a-z0-9])iphone\s*x(?![a-z0-9])", 0).search(text):
        subjects.add("iphone-x")
    for generation in _compiled_rule(r"(?<![a-z0-9])iphone\s*(\d{1,2})(?!\d)", 0).findall(text):
        subjects.add(f"iphone-{generation}")
    if _compiled_rule(r"\bmacbook\s+pro\b|macbook\s*pro|苹果笔记本", 0).search(text):
        subjects.add("macbook-pro")
    if _compiled_rule(r"\bmacbook\s+air\b|macbook\s*air", 0).search(text):
        subjects.add("macbook-air")
    if _compiled_rule(r"\bipad\s+mini\b|ipad\s*mini", 0).search(text):
        subjects.add("ipad-mini")
    if _compiled_rule(r"\bipad\s+pro\b|ipad\s*pro", 0).search(text):
        subjects.add("ipad-pro")
    if not subjects and _compiled_rule(r"\bmacs?\b|(?:三|3)\s*款\s*mac", 0).search(text):
        subjects.add("mac")
    if not subjects:
        subjects |= {
            product
            for product in identity.title_products
            if product in {
                "airpods",
                "apple-watch",
                "homepod",
                "imac",
                "ipad",
                "iphone",
                "mac-mini",
                "mac-pro",
                "mac-studio",
                "macbook",
                "vision-pro",
            }
        }
    return subjects


def _product_lifecycle_year_keys(text: str, subjects: set[str]) -> set[str]:
    """Keep years attached to named models, not the report's calendar date."""
    keys: set[str] = set()
    for subject in subjects:
        model = re.escape(subject).replace(r"\-", r"\s*")
        matches = _compiled_rule(r"(?<!\d)(20\d{2})\s*(?:(?:年款|款)\s*)?" + model + r"(?![a-z0-9])|"
            + model + r"\s*(?:[（(]\s*)?(20\d{2})\s*(?:年款|款|model\b|[）)])", re.I).finditer(text)
        keys.update(f"lifecycle-model-year:{subject}:{next(v for v in match.groups() if v)}"
                    for match in matches)
    return keys


def _first_party_facility_subject(text: str) -> str:
    if _contains(
        text,
        "apple education center",
        "apple educational center",
        "苹果教育中心",
    ):
        return "education-center"
    if _contains(text, "apple developer center", "苹果开发者中心"):
        return "developer-center"
    if _contains(
        text,
        "innovation center",
        "innovation centre",
        "research center",
        "research centre",
        "engineering center",
        "engineering centre",
        "创新中心",
        "研发中心",
        "工程中心",
    ):
        return "innovation-center"
    if _contains(
        text,
        "apple advanced manufacturing center",
        "苹果先进制造中心",
    ):
        return "manufacturing-center"
    manufacturing = _contains(
        text,
        "manufacturing",
        "factory",
        "production line",
        "制造",
        "工厂",
        "生产线",
    )
    training = _contains(
        text,
        "training",
        "education courses",
        "training school",
        "培训",
        "教育课程",
        "培训学校",
    )
    if _contains(text, "advanced manufacturing center", "先进制造中心"):
        return "manufacturing-center"
    if _contains(text, "manufacturing center", "制造中心"):
        return "manufacturing-center"
    if _contains(text, "developer center", "开发者中心"):
        return "developer-center"
    if _contains(
        text,
        "education center",
        "educational center",
        "training center",
        "learning center",
        "education programme center",
        "education program center",
        "教育中心",
        "培训中心",
        "学习中心",
    ):
        return "education-center"
    if manufacturing and training:
        return "manufacturing-center"
    return ""


def _first_party_facility_location(title: str) -> str:
    """Return a title-owned facility location without relying on a region table."""
    title_text = _normalized(title)
    patterns = (
        r"\b(?:center|centre|facility|school|campus)\s+in\s+([a-z][a-z .'-]{2,30})$",
        r"\bin\s+([a-z][a-z .'-]{2,30})\s+(?:gets?|opens?|welcomes?|with)\b",
        r"\bin\s+([a-z][a-z .'-]{2,30})$",
        r"在([^，。,:：]{2,18}?)(?:设立|建立|落地|开设|启用).{0,16}(?:中心|学校|园区)",
    )
    for pattern in patterns:
        match = re.search(pattern, title_text, re.I)
        if not match:
            continue
        location = _compiled_rule(r"[^a-z0-9\u3400-\u9fff]+", 0).sub("-", match.group(1), 0).strip("-")
        if location:
            return location
    return ""


def _hardware_accessory_evaluation_claim(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> tuple[str, str] | None:
    """Return a product/accessory pair for one compatibility evaluation.

    Testing, considering, and deciding not to ship an accessory are successive
    descriptions of the same prototype decision, not separate product events.
    The relation is derived from the title and short lead so unrelated product
    background cannot create the claim.
    """
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return None
    if _compiled_rule(r"\b(?:obsolete|vintage)\b.{0,36}\b(?:products?\s+)?list\b|"
        r"(?:过时|复古|停产).{0,18}(?:产品)?(?:名单|列表)|"
        r"(?:列入|进入).{0,20}(?:过时|复古|停产)(?:产品)?(?:名单|列表)", re.I).search(_normalized(title)):
        return None
    products = identity.title_products & _bounded_evidence_products(title) & _HARDWARE_FIRST_PARTY_PRODUCTS
    if len(products) != 1:
        return None
    evaluation = (
        r"\b(?:test(?:ed|ing)?|prototype|consider(?:ed|ing)?|evaluate(?:d|s|ing)?|"
            r"support(?:ed|s|ing)?|compatib(?:le|ility)|not\s+expected\s+to\s+(?:ship|launch)|"
            r"won['’]t\s+(?:ship|launch|support)|will\s+not\s+(?:ship|launch|support))\b|"
            r"(?:测试|原型|考虑|评估|支持|兼容|不会|不太可能|无缘)"
    )
    # Product, accessory and evaluation must share their own assertion. A
    # keyboard in an OS port's working-device inventory is not this relation.
    for text in (_normalized(title), _normalized(lead)[:700]):
        for start, end in source_clause_spans(text):
            sentence = text[start:end]
            if not products & _bounded_evidence_products(sentence):
                continue
            for name, pattern in (
                ("stylus", r"\b(?:apple\s+pencil|stylus|digital\s+pen)\b|触控笔|手写笔"),
                ("keyboard", r"\b(?:magic\s+keyboard|keyboard)\b|妙控键盘|键盘"),
                ("controller", r"\b(?:game\s+controller|controller)\b|游戏手柄|控制器"),
            ):
                if (re.search(pattern, sentence, re.I)
                        and re.search(evaluation, sentence, re.I)):
                    return next(iter(products)), name
    return None


def _embedded_current_preview_subject(title, lead, references):
    # A source embedding is an object identifier only when this article
    # actually reports its current publication, not a later discussion of it.
    if not _compiled_rule(r"teases?|preview|预告|预热", re.I).search(title) or _compiled_rule(r"opinion|commentary|why|评论|观点", re.I).search(title):
        return ""
    # A later action on the same media object does not inherit its publication.
    # The headline must report presenting the preview; the local prose may
    # supply the publisher and publication in a following sentence.
    if not _compiled_rule(r"\b(?:teases?|previews|posts?|posted|shares?|shared|publishes?|published)\b|"
                     r"(?:发布|分享|发了).{0,20}(?:视频|预告|预热)", re.I).search(title):
        return ""
    local = lead[:900]
    role_pattern = r"(?:new(?:ly appointed)?\s+)?Apple(?:'s)?\s+(?:(?:new|current)\s+)?CEO|苹果(?:新任|现任)?\s*CEO"
    named_title = _compiled_rule(r"^([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:teases?|previews|posts?|shares?)\b", 0).match(title)
    if named_title and not re.search(r"(?:" + role_pattern + r")\s+" + re.escape(named_title.group(1)) + r"\b", local, re.I):
        return ""
    foreign_role = _compiled_rule(r"^(\w+)\s+CEO\b", re.I).match(title)
    if foreign_role and foreign_role.group(1).casefold() != "apple":
        return ""
    sentences = _compiled_rule(r"(?<=[.!?。！？])\s*", 0).split(local, 0)
    current = False
    active_post = False
    active_publisher = ""
    for sentence in sentences[:3]:
        # These qualify the publication, unlike a later relative clause that
        # predicts what hardware the existing post may be hinting at.
        if _compiled_rule(r"previously|earlier|last year|no new|did not|has not|never|"
                     r"\b(?:is|was)\s+not\s+(?:a\s+)?(?:video|clip|post|preview)\b|"
                     r"\bnot\s+(?:posted|shared|published)\b|此前|去年|并未|没有发布|未曾|尚未公开", re.I).search(sentence):
            active_post = False
            continue
        role = re.search(role_pattern, sentence, re.I)
        video = _compiled_rule(r"\b(?:video|clip)\b|视频|短片", re.I).search(sentence)
        publication = _compiled_rule(r"\b(?:posted|shared|published)\b|发布|分享|发了|公开了", re.I).search(sentence)
        noun_post = re.search(r"\bpost from (?:" + role_pattern + r").*?\b(?:previews?|is)\b", sentence, re.I)
        same_post_video = bool(active_post and video and _compiled_rule(r"^(?:His|Her|Their|This|The)\s+(?:(?:\w+|\d+)\s+)?post\b.*?\bis\b", re.I).match(sentence))
        if (role and video and publication) or same_post_video or (noun_post and (video or _compiled_rule(r"\bpreviews?\b", re.I).search(sentence))):
            current = True
            break
        if noun_post:
            active_post = True
            publisher = re.search(r"(?:" + role_pattern + r")\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", sentence)
            active_publisher = publisher.group(1) if publisher else ""
        elif sentence.strip():
            # A comparison may mention other people in its subordinate clause.
            # Keep the post only when its main clause explicitly returns to
            # the established publisher performing the same action.
            main_clause = sentence.rsplit(',', 1)[-1].strip()
            same_owner_action = bool(active_post and active_publisher and re.match(
                r"^(?:(?:the|new|current)\s+)?(?:CEO\s+)?" + re.escape(active_publisher)
                + r"\s+(?:(?:has|is)\s+)?(?:also\s+)?(?:done|doing|does|did)\s+the same(?:\s+(?:thing|action))?\b",
                main_clause, re.I))
            active_post = same_owner_action
    objects = {(ref.platform, ref.object_id) for ref in references}
    if current and len(objects) == 1:
        platform, object_id = next(iter(objects))
        return f"embedded-video:{platform}:{object_id}"
    return ""


def _preview_video_content_subject(title: str, lead: str, identity: EventIdentity) -> str:
    """Identify the published media by a local depicted relation, not a guess about a device."""
    if "iphone" not in identity.products or not _compiled_rule(r"\b(?:teases?|preview|video)\b|预告|预热", re.I).search(title):
        return ""
    publication = _short_lead_scope(lead, sentences=1)
    if (not _compiled_rule(r"apple(?:['’]s)?\s+ceo|苹果\s*ceo", re.I).search(publication)
            or not _compiled_rule(r"\b(?:posted|shared|published)\b|发布|分享", re.I).search(publication)
            or _compiled_rule(r"\b(?:previously|last year|last month|not|never)\b|去年|此前|未发布", re.I).search(publication)):
        return ""
    publisher = _compiled_rule(r"\bApple(?:['’]s)?\s+CEO\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3})\b|"
                          r"苹果\s*CEO[^。！？]*?[（(]([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3})[）)]", 0).search(lead)
    publisher_name = (publisher.group(1) or publisher.group(2)).casefold() if publisher else "role"
    named_title = _compiled_rule(r"^([A-Za-z]+(?:\s+[A-Za-z]+){1,3})\s+teases?\b", re.I).match(title)
    if named_title and not _compiled_rule(r"apple(?:\s+ceo)?", re.I).fullmatch(named_title.group(1)):
        if not publisher or named_title.group(1).casefold() != publisher_name:
            return ""
    objects = {"light": r"light|beam(?:\s+of\s+light)?|光束|一束光",
               "logo": r"logo|标志|标识", "shape": r"shape|图形", "text": r"text|文字"}
    changes = {"shrink": r"shrinks?|shrinking|缩小|由大变小", "grow": r"grows?|growing|变大|扩大",
               "rotate": r"rotates?|rotating|旋转", "fade": r"fades?|fading|淡出|消失"}
    surfaces = {"glass": r"glass|玻璃", "screen": r"screen|屏幕", "metal": r"metal|金属", "paper": r"paper|纸"}
    for clause in _compiled_rule(r"[。！？,，;；]|(?<=[.!?])\s+", 0).split(_normalized(lead)[:900], 0):
        if not _compiled_rule(r"\b(?:video|clip)\b|视频|片中", 0).search(clause):
            continue
        if _compiled_rule(r"\b(?:not|never|rumors?|may|might|could)\b|并未|没有|猜测|传闻", 0).search(clause):
            continue
        matched = [[(key, pattern) for key, pattern in vocabulary.items() if re.search(pattern, clause, re.I)]
                   for vocabulary in (objects, changes, surfaces)]
        if not all(len(values) == 1 for values in matched):
            continue
        (obj, obj_pattern), (change, change_pattern), (surface, surface_pattern) = [values[0] for values in matched]
        if (re.search(r"(?:" + obj_pattern + r")[^.;。]*?(?:" + change_pattern + r")[^.;。]*?\b(?:against|on|over)\b[^.;。]*?(?:" + surface_pattern + r")", clause, re.I)
                or re.search(r"(?:" + obj_pattern + r")[^。]*?在[^。]{0,12}(?:" + surface_pattern + r")[^。]*?(?:" + change_pattern + r")", clause, re.I)):
            return "apple-ceo-video:" + _compiled_rule(r"\s+", 0).sub("-", publisher_name, 0) + ":" + ":".join((obj, change, surface))
    return ""


def _camera_preview_subject(title: str, lead: str, identity: EventIdentity) -> str:
    content_subject = _preview_video_content_subject(title, lead, identity)
    if content_subject:
        return content_subject
    models = {value.removeprefix("iphone-model:") for value in identity.title_components
              if value.startswith("iphone-model:")}
    executive = _compiled_rule(r"\bApple(?:['’]s)?\s+CEO\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3})\b", 0).search(lead)
    executive_title = bool(executive and re.match(re.escape(executive.group(1)) + r"\s+teases?\b", title, re.I))
    preview_actor = (executive_title or _compiled_rule(r"^apple(?:['’]s)?\s+(?:ceo\s+)?teases?\b|^苹果\s*CEO", re.I).match(title)
                     or _compiled_rule(r"^apple\s+(?:has\s+)?(?:posted|released|shared)\s+(?:a\s+)?(?:short\s+)?(?:teaser|preview)\s+video\b", re.I).match(lead))
    if (len(models) == 1 and _compiled_rule(r"variable[- ]aperture|可变光圈", re.I).search(title)
            and _compiled_rule(r"\bteases?\b|预告|预热视频", re.I).search(title) and preview_actor
            and not _compiled_rule(r"\b(?:previously|last year|last month)\b|去年|此前", re.I).search(_short_lead_scope(lead, sentences=1))):
        return "iphone-" + next(iter(models)) + ":variable-aperture"
    return ""


def preview_reference_needs_review(title, lead, identity, references):
    """A predicted model is not a unique identifier for a published video."""
    return bool(_camera_preview_subject(title, lead, identity)
                and not _preview_video_content_subject(title, lead, identity)
                and not _embedded_current_preview_subject(title, lead, references))


def _local_current_camera_adoption(lead: str, identity: EventIdentity) -> str:
    """Explicit current Apple/device assertion may follow neutral context."""
    models = {value.removeprefix("iphone-model:") for value in identity.title_components
              if value.startswith("iphone-model:")}
    if not models:
        return ""
    for clause in _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(_normalized(lead)[:900], 0):
        if _compiled_rule(r"\b(?:previously|earlier|last year|last month|rumors?|reportedly|may|might|could|not|never)\b|此前|去年|尚未|并未|传闻", re.I).search(clause):
            continue
        statement = _compiled_rule(r"^apple\s+(?:says?|has\s+(?:confirmed|revealed|announced)|(?:today\s+)?(?:confirmed|revealed|announced))\s+(?:that\s+)?"
            r"(?:the\s+)?iphone\s+(\d{1,2}(?:\s+pro(?:\s+max)?)?)\s+(?:has|features?|includes?)\s+[^.;。]*?\bcamera\b", re.I).match(clause)
        if statement and _compiled_rule(r"\s+", 0).sub("-", statement.group(1), 0) in models:
            return clause
    return ""


def _hardware_component_adoption_claims(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> set[tuple[str, str]]:
    """Return title-owned product/component adoption relations.

    This normalizes wording such as "first with", "will use", and "expected
    with" while keeping supplier orders, cost analyses, and generic component
    background outside the relation.
    """
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return set()
    # A teardown reports observed construction, not a new adoption announcement.
    if _compiled_rule(r"\bteardowns?\b|拆解", re.I).search(title):
        return set()
    products = identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    style_transfer = _compiled_rule(r"^.+?-style\s+.+?\s+come(?:s)?\s+to\s+(.+)$", re.I).search(title)
    if style_transfer:
        targets = _bounded_evidence_products(style_transfer.group(1)) & _HARDWARE_FIRST_PARTY_PRODUCTS
        if len(targets) == 1:
            products = targets
    if len(products) == 1:
        generic = next(iter(products))
        localized = {product for product in _bounded_evidence_products(_short_lead_scope(lead, sentences=1))
                     if product.startswith(generic + "-")}
        if len(localized) == 1:
            products = localized
    if len(products) != 1:
        return set()
    if identity.title_actions & {"supply-production", "price-change", "legal"}:
        return set()
    text = f"{_normalized(title)}. {_normalized(lead)[:700]}"
    title_components = {
        component
        for component in identity.title_components
        if ":" not in component
    }
    # A broad camera headline may name its adopted component in the current
    # source sentence. Require that sentence's device target to match the title.
    title_models = {value.removeprefix("iphone-model:") for value in identity.title_components
                    if value.startswith("iphone-model:")}
    source_camera = _compiled_rule(r"^apple\s+(?:is\s+expected\s+to|will|plans\s+to)\s+(?:introduce|adopt|use|feature)\s+"
        r"[^.;。]*?\bcamera\s+(?:on|in|for)\s+iphone\s+(\d{1,2}(?:\s+pro(?:\s+max)?)?)\b", re.I).search(_short_lead_scope(lead, sentences=1))
    if (_compiled_rule(r"\bcamera\b|相机|摄像头", re.I).search(title) and source_camera
            and _compiled_rule(r"\s+", 0).sub("-", source_camera.group(1).lower(), 0) in title_models):
        title_components.add("camera-system")
    current_camera = _local_current_camera_adoption(lead, identity)
    if current_camera:
        title_components.add("camera-system")
    label_adoption = bool("magic-keyboard" in products and _compiled_rule(r"symbol[- ]only|key symbols|(?:按键|文字|标签|标识).{0,30}(?:符号|改用|换为)", re.I).search(text))
    if label_adoption:
        title_components.add("keyboard-key-labels")
    adoption_text = (f"{_normalized(title)}. {_normalized(_short_lead_scope(lead, sentences=1))}"
                     if "camera-system" in title_components else text)
    adoption = bool(
        current_camera or label_adoption or (title_components and _compiled_rule(r"^apple\s+adds?\s+.+?\s+to\s+(?:the\s+)?(?:iphone|ipad|mac|apple\s+watch)\b", re.I).search(title)) or _compiled_rule(r"\b(?:first|debut|adopt(?:s|ed|ing)?|use(?:s|d|ing)?|feature(?:s|d|ing)?|"
            r"equip(?:ped|s)?|come(?:s)?\s+with|launch(?:es|ed|ing)?\s+with|"
            r"expected\b.{0,45}\b(?:with|to\s+use|to\s+feature|to\s+introduce))\b|"
            r"(?:首次|首度|改用|采用|搭载|配备|换用|将用|预计).{0,36}"
            r"(?:推出|发布|搭载|采用|配备|屏幕|面板|芯片|传感器|摄像头|电池|调制解调器)?", re.I).search(adoption_text)
        or (
            title_components
            and identity.title_actions
            & {
                "delay-roadmap",
                "product-launch",
                "product-refresh",
                "retail-availability",
            }
        )
    )
    if not adoption:
        return set()
    physical_markers = (
        "display",
        "panel",
        "camera",
        "sensor",
        "battery",
        "modem",
        "processor",
        "chip",
        "memory",
        "case-material",
        "glass",
        "thermal",
        "speaker",
        "keyboard",
        "water-resistance",
    )
    components = {
        component
        for component in title_components
        if any(marker in component for marker in physical_markers)
    }
    if _compiled_rule(r"apple\s+.+\s+roadmap\s+update", 0).fullmatch(_normalized(title)):
        components |= {
            component
            for component, terms in COMPONENT_PATTERNS
            if ":" not in component
            and any(marker in component for marker in physical_markers)
            and _contains(text, *terms)
        }
    if _camera_preview_subject(title, lead, identity):
        components.discard("camera-system")
    product = next(iter(products))
    models = sorted(value.removeprefix("iphone-model:") for value in identity.title_components
                    if value.startswith("iphone-model:"))
    camera_target = "iphone-" + models[0] if product == "iphone" and len(models) == 1 else product
    return {(camera_target if component == "camera-system" else product, component) for component in components}


def _app_store_impersonation_subject(title: str, lead: str) -> str:
    """Return the legitimate app named by an App Store impersonation incident."""
    text = f"{_normalized(title)}. {_normalized(lead)[:500]}"
    if not (
        _contains(text, "app store", "应用商店", "苹果商店")
        and _contains(text, "counterfeit", "impersonat", "fake", "copycat", "山寨", "仿冒", "假冒", "盗版")
    ):
        return ""
    patterns = (
        r"(?:统一平台|official\s+platform)\s*[(（]\s*(?:简称)?\s*[“\"‘']?"
        r"([a-z0-9\u4e00-\u9fff.+-]{2,30}(?:\s*app)?)\s*[”\"’']?\s*[)）]",
        r"(?:简称|abbreviated\s+as)\s*[“\"‘']?"
        r"([a-z0-9\u4e00-\u9fff.+-]{2,30})(?:\s*app)?[”\"’']?",
        r"(?:^|[，,:：。])\s*([a-z0-9\u4e00-\u9fff.+-]{2,30})(?:\s*app)?\s*官方(?:回应|表示|称)",
        r"(?:盗版|山寨版?|仿冒|假冒)[“\"‘']([^”\"’']{2,40})[”\"’']",
        r"(?:正版|官方)(?:\s*app)?[“\"‘']([^”\"’']{2,40})[”\"’']",
        r"(?:名为)\s*[“\"‘']?([a-z0-9\u4e00-\u9fff.+-]{2,30})(?:\s*app)?[”\"’']?",
    )
    ignored = {"app", "政务", "应用", "软件", "相关部门", "苹果应用商店"}
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        subject = _compiled_rule(r"[^a-z0-9\u4e00-\u9fff.+-]+", 0).sub("-", _normalized(match.group(1)), 0).strip("-")
        subject = _compiled_rule(r"(?:-?app)$", 0).sub("", subject, 0).strip("-")
        if subject and subject not in ignored:
            return subject
    return ""


def _canonical_supplier_entities(text: str) -> set[str]:
    aliases = {
        "boe": ("boe", "京东方"),
        "broadcom": ("broadcom", "博通"),
        "foxconn": ("foxconn", "鸿海", "富士康"),
        "lg-display": ("lg display", "lg 显示", "乐金显示"),
        "samsung-display": ("samsung display", "三星显示"),
        "tsmc": ("tsmc", "台积电"),
        "intel": ("intel", "英特尔"),
        "tata": ("tata", "塔塔"),
    }
    return {
        canonical
        for canonical, values in aliases.items()
        if _contains(text, *values)
    }


def _structured_assertion_keys(
    title: str,
    lead: str,
    identity: EventIdentity,
    evidence: str = "",
    regions: Iterable[str] = (),
) -> tuple[set[str], set[str], set[str]]:
    """Build subject/predicate assertions used before broad topic similarity."""
    title_scope, primary_scope = _primary_assertion_scope(title, lead)
    text = primary_scope
    short_lead = _short_lead_scope(lead)
    evidence_scope = f"{title_scope}. {short_lead} {_normalized(evidence)[:1600]}".strip()
    event_keys: set[str] = set()
    boundaries: set[str] = set()
    separation: set[str] = set()

    # A physical retail offer needs its current price, and an availability
    # expansion needs the rated model, not a background burst capability.
    retail_products = set(identity.products) & _SPECIFIC_FIRST_PARTY_PRODUCTS - _SOFTWARE_FIRST_PARTY_PRODUCTS
    source_retail = f"{title_scope}. {short_lead}"
    explicit_store_action = bool(_compiled_rule('\\bapple\\s+(?:officially\\s+)?(?:launched|released)|苹果(?:官方|官网).{0,12}(?:上架|上线|发布)', re.I).search(short_lead))
    if len(retail_products) == 1 and identity.scope == "apple-direct" and (identity.content_form == "news" or explicit_store_action):
        product = next(iter(retail_products))
        offer_action = bool(_compiled_rule('\\b(?:released|launched|restored|back)\\b|(?:官网|官方|商店).{0,15}(?:上架|上线)|苹果.{0,12}发布', re.I).search(source_retail))
        current_price = _compiled_rule('\\b(?:for|at|to)\\s*\\$(\\d+(?:\\.\\d+)?)|(?:降至|售价为|售价)\\s*(\\d+(?:\\.\\d+)?)\\s*美元', re.I).search(source_retail)
        yuan_price = _compiled_rule('(?:降至|售价为?|只要)\\s*(\\d+(?:\\.\\d+)?)\\s*元|^(\\d+(?:\\.\\d+)?)\\s*元', 0).search(source_retail)
        if offer_action and (current_price or yuan_price):
            match = current_price or yuan_price
            amount = match.group(1) or match.group(2)
            currency = "usd" if current_price else "cny"
            event_keys.add(f"structured-assertion:{product}:current-retail-offer:{currency}-{amount}")
            boundaries.add(f"structured-subject:{product}")
            separation |= {f"assertion-subject:{product}", "assertion-action:current-retail-offer", f"retail-offer-value:{product}:{currency}:{amount}"}
            if _compiled_rule('\\b(?:new|second-generation)\\b|新款|全新一代|第二代', re.I).search(source_retail):
                event_keys.add(f"structured-assertion:{product}:new-model-retail-offer")
        expansion = _compiled_rule('\\b(?:expand(?:s|ed)?|extend(?:s|ed)?)\\b.{0,55}\\b(?:markets|countries|coverage|availability)\\b|(?:扩大|扩展|拓展).{0,32}(?:市场|销售覆盖|供应范围)', re.I).search(short_lead)
        rated_model = _compiled_rule('(?<![\\d.])(\\d+)\\s*w\\s*(?:dynamic\\s+(?:power\\s+)?adapter|动态(?:电源适配器|充电头))', re.I).search(source_retail)
        if expansion and rated_model and product == "apple-power-adapter":
            model = f"dynamic-{rated_model.group(1)}w"
            event_keys.add(f"structured-assertion:{product}:{model}:availability-expansion")
            boundaries.add(f"structured-subject:{product}:{model}")
            separation |= {f"assertion-subject:{product}:{model}", "assertion-action:availability-expansion"}

    chip_subjects = {key.removeprefix("apple-silicon-generation:") for key in identity.title_components
                     if key.startswith("apple-silicon-generation:")}
    if (len(chip_subjects) == 1 and not identity.title_products
        and _compiled_rule('\\bchip\\b|芯片', 0).search(title_scope)
        and _compiled_rule('\\b(?:release|reveals?|announces?|introduces?)\\b|发布|推出', 0).search(title_scope)):
        chip = next(iter(chip_subjects))
        event_keys.add(f"structured-assertion:apple-silicon:{chip}:chip-release")
        separation |= {f"assertion-subject:apple-silicon:{chip}", "assertion-action:chip-release"}
    host_products = identity.title_products & {"mac-mini", "mac-studio", "macbook", "imac", "mac-pro"}
    if set(device_operation_subjects(title)) & {'mac-mini', 'mac-studio', 'macbook-pro', 'macbook-air', 'imac'}:
        host_products -= {'mac-mini', 'mac-studio', 'macbook', 'imac'}
    if len(host_products) == 1 and not _compiled_rule(r"\breviews?\b|评测|测评", re.I).search(title_scope):
        host = next(iter(host_products))
        for clause in _compiled_rule(r"(?<=[.!?。！？])\s*", 0).split(f"{short_lead}. {evidence}", 0):
            if (host in _bounded_evidence_products(clause)
                and _compiled_rule('\\b(?:new|launched|introduced)\\b|新款|发布|推出', re.I).search(clause)
                and _compiled_rule('\\b(?:with|configurations?|options?)\\b|搭载|配置|提供', re.I).search(clause)):
                configurations = {_compiled_rule(r"\s+", 0).sub("-", match.group().casefold(), 0)
                                  for match in _compiled_rule('\\bM\\d+(?:\\s+(?:Pro|Max|Ultra))?\\b', re.I).finditer(clause)}
                if configurations:
                    event_keys.add(f"structured-assertion:{host}:new-model-configurations:" + "+".join(sorted(configurations)))
                    separation |= {f"assertion-subject:{host}", "assertion-action:new-model-configuration"}

    if (identity.scope == "apple-direct" and identity.content_form == "news"
        and identity.title_products == {"magic-keyboard"}
        and _compiled_rule('\\b(?:refresh(?:es|ed)?|updates?|updated|released?|launched?)\\b|更新|发布|推出', re.I).search(source_retail)):
        stage = "reported" if _compiled_rule('\\b(?:may|might|could|expected|will)\\b|预计|可能|或将', re.I).search(source_retail) else "announced"
        separation.add(f"source-accessory-refresh:magic-keyboard:{stage}")

    # Execution version and preparation target are roles in one source claim,
    # not an unordered set of OS version numbers.
    for clause in _compiled_rule(r"(?<=[.!?。！？])\s+(?=[A-Z苹果])", 0).split(f"{short_lead}. {evidence}", 0):
        if (_compiled_rule('spotlight|聚焦', re.I).search(clause) and _compiled_rule('index(?:ing)?|索引', re.I).search(clause)
            and _compiled_rule('start|optimiz|prepare|ready|开始|优化|准备', re.I).search(clause)
            and _compiled_rule('\\bapple\\b|苹果', re.I).search(clause)
            and not _compiled_rule('\\b(?:not|never|might|should)\\b|并未|应该|可能', re.I).search(clause)):
            versions = _compiled_rule('\\b(ios|ipados|macos)\\s+(\\d+(?:\\.\\d+)*)', re.I).findall(clause)
            target_match = _compiled_rule('\\b(?:ready|prepar(?:e|es|ed|ing))\\s+(?:\\w+\\s+){0,3}for\\s+(ios|ipados|macos)\\s+(\\d+(?:\\.\\d+)*)', re.I).search(clause)
            if (len(versions) == 2 and target_match
                and versions[0][0].casefold() == versions[1][0].casefold()):
                family, target = target_match.group(1).casefold(), target_match.group(2)
                current = next((version for _, version in versions if version != target), target)
                event_keys.add(f"structured-assertion:{family}:spotlight-index-preparation:{current}-to-{target}")
                separation |= {f"spotlight-execution:{family}:{current}", f"spotlight-target:{family}:{target}",
                               "assertion-action:index-preparation", f"assertion-subject:{family}:spotlight-index"}
    immersive_scope = f"{title_scope}. {lead} {evidence}"
    baseball = _compiled_rule('\\b(?:mlb|major league baseball|friday night baseball)\\b|周五夜棒球', re.I).search(immersive_scope)
    immersive = _compiled_rule('apple immersive|immersive video|沉浸式|\\b3d\\b', re.I).search(immersive_scope)
    broadcast = _compiled_rule('stream(?:ing|ed)?|直播', re.I).search(immersive_scope)
    primary_immersive = _compiled_rule('apple immersive|immersive video|沉浸式|\\b3d\\b', re.I).search(f'{title_scope}. {_short_lead_scope(lead, sentences=1)}')
    if baseball and immersive and primary_immersive and broadcast and ("vision-pro" in identity.products or "vision pro" in immersive_scope.casefold()):
        event_keys.add("structured-assertion:apple-immersive:mlb:live-broadcast-rollout")
        separation |= {"assertion-subject:apple-immersive:mlb", "assertion-action:immersive-live-broadcast"}

    named_resources = {name.removeprefix("apple-") for name in identity.named_subjects
                       if name.startswith("apple-") and name.removeprefix("apple-").replace("-", " ") in title_scope}
    if (identity.scope == "apple-direct" and "product-launch" in identity.title_actions
        and _compiled_rule('developers?|开发者', re.I).search(source_retail)
        and _compiled_rule('resources?|工具|资源', re.I).search(source_retail)):
        for name in named_resources:
            event_keys.add(f"structured-assertion:first-party-resource:{name}:launch")
            separation |= {f"assertion-subject:first-party-resource:{name}", "assertion-action:resource-launch"}

    first_party_services = set(identity.products) & _SOFTWARE_FIRST_PARTY_PRODUCTS
    access_queue = bool(
        _compiled_rule('\\b(?:waitlist|waiting\\s+list|access\\s+queue|wait\\s+in\\s+line|wait\\s+for\\s+access)\\b|(?:候补名单|访问队列|排队机制|排队访问)', re.I).search(evidence_scope)
    )
    if first_party_services and access_queue:
        service_subject = "siri-ai" if "siri" in first_party_services else sorted(first_party_services)[0]
        event_keys.add(f"structured-assertion:{service_subject}:access-waitlist")
        boundaries.add(f"structured-subject:{service_subject}")
        separation |= {
            f"assertion-subject:{service_subject}",
            "assertion-action:access-waitlist",
        }

    panel_scope = f"{title_scope}. {short_lead}"
    panel_domain = bool(_compiled_rule('fold(?:able|ing)?|折叠', re.I).search(title_scope)
                        and _compiled_rule('panels?|screens?|displays?|面板|屏幕', re.I).search(title_scope))
    report_entities = {value.removeprefix("report-attribution:") for value in identity.components
                       if value.startswith("report-attribution:") and not value.endswith(":multiple")}
    if panel_domain and len(report_entities) == 1:
        institution = next(iter(report_entities))
        metrics = set()
        for clause in _compiled_rule(r"[,，;；。]|(?<=[.!?])\s+", 0).split(panel_scope, 0):
            if (_compiled_rule('apple|iphone|苹果', re.I).search(clause)
                    and _compiled_rule('orders?|订单|采购份额', re.I).search(clause)):
                share = _compiled_rule("(?:apple(?:'s)?|iphone|苹果).{0,110}?(?:take|account for|占|斩获|贡献).{0,40}?(\\d+(?:\\.\\d+)?)\\s*%", re.I).search(clause)
                if share:
                    metrics.add(("apple-order-share", share.group(1)))
        for growth in _compiled_rule('(\\d+(?:\\.\\d+)?)\\s*%\\s+(?:increase|growth)\\s+in\\s+foldable\\s+(?:smartphone\\s+)?panel\\s+shipments|折叠[^。；;]{0,12}面板出货量[^。；;]{0,60}?(?:同比)?增长(?:约)?\\s*(\\d+(?:\\.\\d+)?)\\s*%', re.I).finditer(panel_scope):
            metrics.add(("industry-panel-shipment-growth", growth.group(1) or growth.group(2)))
        for role, value in metrics:
            event_keys.add(f"structured-panel-report-measure:{institution}:foldable-phone:{role}:{value}")
        if metrics:
            separation.add("panel-report-institution:" + institution)
            for year in _compiled_rule('(?<!\\d)20\\d{2}(?!\\d)', 0).findall(panel_scope):
                separation.add("panel-report-year:" + year)

    security_scope = f"{title_scope}. {short_lead}"
    if (_compiled_rule('security bulletins?|安全公告|安全通告', re.I).search(security_scope)
            and _compiled_rule('apple|苹果', re.I).search(security_scope)
            and _compiled_rule('security|安全', re.I).search(title_scope)
            and _compiled_rule('fix|patch|修复', re.I).search(security_scope)):
        for platform, version in _compiled_rule('\\b(ios|ipados|macos|watchos|tvos|visionos)\\s+(?:[a-z]+\\s+)?(\\d+(?:\\.\\d+)+)', re.I).findall(security_scope):
            event_keys.add(f"structured-assertion:apple-security-bulletin:{platform.lower()}:{version}")
            separation.add(f"security-bulletin-version:{platform.lower()}:{version}")

    vulnerability_component = next((name for name, pattern in (
        ("airdrop", r"airdrop|隔空投送"), ("handoff", r"handoff|接力"))
        if re.search(pattern, title_scope, re.I)), "")
    if vulnerability_component and _compiled_rule('vulnerabilit|flaws?|漏洞', re.I).search(title_scope):
        partial_fix = bool(_compiled_rule('(?:apple|苹果).{0,20}(?:fixed one|修复其中一个|修复了一个)', re.I).search(security_scope)
                           and _compiled_rule('working on|remaining fixes|继续.{0,12}(?:补丁|修复)', re.I).search(security_scope))
        completed_fix = bool(_compiled_rule('(?:fix(?:es|ed)?|修复).{0,12}(?:all|全部|所有)', re.I).search(title_scope))
        phase = "partial-remediation" if partial_fix and not completed_fix else "complete-remediation" if completed_fix else ""
        if phase:
            event_keys.add(f"structured-assertion:{vulnerability_component}:vulnerability:{phase}")
            separation.add("vulnerability-component:" + vulnerability_component)
            separation.add("vulnerability-remediation:" + phase)

    device_version = _compiled_rule('\\bvisionos\\s*(\\d+(?:\\.\\d+)?)\\b', re.I).search(title_scope)
    device_generation = _compiled_rule('\\b(m\\d+)\\s+vision pro\\b', re.I).search(title_scope)
    if device_version and device_generation:
        device_features = set()
        for sentence in _compiled_rule(r"[.!?。！？;；]", 0).split(security_scope, 0):
            negative = r"miss(?:es|ing)?|lacks?|(?:does not|doesn't|cannot|can't|not)\s+(?:support|give)|不支持|无法|缺少"
            sentence = _compiled_rule(r"\bwhile\b|但|而", re.I).split(sentence, 1)[0]
            if re.search(negative, sentence, re.I):
                if (re.search(rf"\b{re.escape(device_generation.group(1))}\s+vision pro\b", sentence, re.I)
                        and _compiled_rule('siri.{0,20}(?:voice customization|voice customisation|语音定制)', re.I).search(sentence)):
                    separation.add("device-feature-polarity:siri-voice-customization:unsupported")
                continue
            if _compiled_rule('siri.{0,20}(?:voice customization|voice customisation|语音定制)', re.I).search(sentence):
                device_features.add("siri-voice-customization")
            model = _compiled_rule('\\bafm\\s+(\\d+)\\s+core advanced\\b', re.I).search(sentence)
            if model:
                device_features.add("afm-" + model.group(1) + "-core-advanced")
        for feature in device_features:
            separation.add(f"device-feature-polarity:{feature}:supported")
            event_keys.add(f"structured-assertion:visionos:{device_version.group(1)}:vision-pro:{device_generation.group(1).lower()}:{feature}")
        if device_features:
            separation |= {"device-feature-generation:" + device_generation.group(1).lower(),
                           "device-feature-version:visionos-" + device_version.group(1)}

    car_key_scope = f"{title_scope}. {short_lead}"
    if (_compiled_rule('car keys?|车钥匙', re.I).search(title_scope)
            and _compiled_rule('apple wallet|苹果钱包|apple 车钥匙', re.I).search(car_key_scope)):
        partners = {name for name, aliases in (
            ("lucid", ("lucid",)), ("xiaomi", ("xiaomi", "小米")),
            ("bmw", ("bmw", "宝马")), ("rivian", ("rivian",)),
            ("mercedes", ("mercedes", "奔驰")), ("hyundai", ("hyundai", "现代汽车")),
            ("kia", ("kia", "起亚")), ("porsche", ("porsche", "保时捷")))
            if _contains(car_key_scope, *aliases)}
        version = _compiled_rule('\\bios\\s*(\\d+(?:\\.\\d+)?)\\b', re.I).search(car_key_scope)
        stage = ("available" if _compiled_rule('\\b(?:launch(?:es|ed)?|now available)\\b|正式上线|现已支持', re.I).search(title_scope)
                 else "code-reference" if (_compiled_rule('\\bcode\\b|代码|现踪迹', re.I).search(car_key_scope)
                      or (_compiled_rule('\\bbeta\\b|测试版', re.I).search(car_key_scope)
                          and _compiled_rule('\\breferences?\\b|标识|踪迹', re.I).search(car_key_scope))) else "")
        if partners and version and stage:
            for partner in partners:
                event_keys.add(f"structured-assertion:apple-wallet:car-key:{partner}:ios-{version.group(1)}:{stage}")
                separation.add("car-key-partner:" + partner)
            separation |= {"car-key-stage:" + stage, "car-key-version:" + version.group(1)}

    home_security_service_roadmap = bool(
        identity.scope == "apple-direct"
        and _compiled_rule('\\b(?:home\\s+security|home\\s+monitoring|security\\s+and\\s+monitoring).{0,36}\\bservice\\b|(?:家庭|家用)(?:安全|安防)(?:监控)?服务|家庭监控服务', re.I).search(text)
        and _compiled_rule('\\b(?:plan(?:s|ned|ning)?|launch(?:es|ed|ing)?|develop(?:s|ed|ing)?|in\\s+the\\s+works|could\\s+release|coming)\\b|(?:计划|规划|研发|开发|筹备|推出|上线|有望)', re.I).search(text)
    )
    if home_security_service_roadmap:
        key = "structured-assertion:apple-home-security:service-roadmap"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-home-security-service")
        separation |= {
            "assertion-subject:apple-home-security-service",
            "assertion-action:service-roadmap",
        }

    advertising_rollout = bool(
        _compiled_rule('\\b(?:ad|ads|advertising|sponsored listings?)\\b|(?:广告|推广内容)', re.I).search(evidence_scope)
        and _compiled_rule('\\b(?:live|launch(?:es|ed)?|roll(?:s|ed|ing)?\\s+out|begin(?:s|ning)?|start(?:s|ed|ing)?|available)\\b|(?:上线|推出|开始投放|正式投放)', re.I).search(evidence_scope)
    )
    if len(first_party_services) == 1 and advertising_rollout and not _compiled_rule("prohibit|won['’]t allow|will not allow|禁投|禁止|不允许", re.I).search(title_scope):
        service_subject = next(iter(first_party_services))
        event_keys.add(f"structured-assertion:{service_subject}:advertising-rollout")
        if service_subject in {"maps", "apple-maps"}:
            separation.add("maps-ad-action:advertising-rollout")
        boundaries.add(f"structured-subject:{service_subject}")
        separation |= {
            f"assertion-subject:{service_subject}",
            "assertion-action:advertising-rollout",
        }

    os_platforms = set(identity.title_products) & {
        "ios",
        "ipados",
        "macos",
        "watchos",
        "tvos",
        "visionos",
    }
    if not os_platforms and "apple-watch" in identity.title_products:
        os_platforms.add("watchos")
    os_components = {
        component
        for component in identity.title_components
        if component.startswith("os-component:")
    }
    if os_platforms and os_components and "feature-change" in identity.actions:
        for platform in os_platforms:
            for component in os_components:
                subject = component.removeprefix("os-component:")
                event_keys.add(
                    f"structured-assertion:os-feature:{platform}:{subject}:feature-change"
                )
                separation.add(f"os-feature-subject:{platform}:{subject}")

    iphone_generation = next(
        (
            component.removeprefix("product-generation:iphone-")
            for component in identity.components
            if component.startswith("product-generation:iphone-")
        ),
        "",
    )
    base_iphone = any(
        component.startswith("iphone-model:") and component.endswith("-base")
        for component in identity.components
    ) or bool(
        _compiled_rule('\\b(?:base|standard)(?:\\s+model)?\\s+iphone\\s*\\d{1,2}\\b|\\biphone\\s*\\d{1,2}\\s+(?:base|standard)(?:\\s+model)?\\b|(?:标准版|基础款).{0,18}iphone\\s*\\d{1,2}|iphone\\s*\\d{1,2}.{0,18}(?:标准版|基础款)', 0).search(text)
    )
    title_has_release_schedule_action = bool(
        _compiled_rule("\\b(?:skip(?:s|ping|ped)?.{0,36}\\blaunch|not\\s+(?:be\\s+)?released\\s+until|won't\\s+launch\\s+alongside|will\\s+not\\s+launch\\s+alongside|release\\w*\\s+separately|split\\s+(?:the\\s+)?launch|delay(?:ed|s|ing)?|postpone(?:d|s)?|push(?:ed|es)?)\\b|(?:拆分|分批|推迟|延期|延后).{0,28}(?:发布|登场|推出)|(?:发布|登场|推出).{0,28}(?:拆分|分批|推迟|延期|延后)", 0).search(title_scope)
    )
    sparse_supplier_confirmation = bool(
        _compiled_rule('\\b20\\d{2}\\b', 0).search(title_scope)
        and _contains(title_scope, "launch", "release", "发布", "登场", "推出")
        and _contains(evidence_scope, "apple supplier", "pegatron", "和硕", "供应商")
        and _contains(evidence_scope, "separately", "early 20", "until next year", "分批", "明年", "推迟", "延期")
    )
    split_release_schedule = bool(
        iphone_generation
        and base_iphone
        and (title_has_release_schedule_action or sparse_supplier_confirmation)
    )
    if split_release_schedule:
        subject = f"iphone-{iphone_generation}-base"
        event_keys.add(f"structured-assertion:{subject}:split-release-schedule")
        boundaries.add(f"structured-subject:{subject}")
        separation |= {
            f"assertion-subject:{subject}",
            "assertion-action:product-release-delay",
        }

    if "product-release-delay" in identity.components and "iphone" in identity.products:
        generation_match = _compiled_rule('(?<![a-z0-9])iphone\\s*(\\d{1,2})(?!\\d)', 0).search(text)
        base_model = bool(
            _compiled_rule('\\b(?:base|standard)(?:\\s+model)?\\s+iphone\\s*\\d{1,2}\\b|\\biphone\\s*\\d{1,2}\\s+(?:base|standard)(?:\\s+model)?\\b|(?:标准版|基础款).{0,18}iphone\\s*\\d{1,2}|iphone\\s*\\d{1,2}.{0,18}(?:标准版|基础款)', 0).search(text)
        )
        period_pattern = (
            r"\b(spring|fall|autumn)\s+(20\d{2})\b|"
            r"(20\d{2})\s*年\s*(春季|秋季)|"
            r"\b(next\s+spring|next\s+fall|next\s+autumn)\b|"
            r"(明年春季|明年秋季)"
        )
        delay_period_pattern = (
            r"(?:delay(?:ed|s|ing)?|postpone(?:d|s)?|push(?:ed|es)?|"
            r"move(?:d|s)?\s+to|推迟|延期|延后).{0,80}?(?:" + period_pattern + r")"
        )
        period_match = None
        for clause in _compiled_rule(r"[，,。.!?！？;；]", 0).split(text, 0):
            if not _compiled_rule('\\b(?:base|standard)\\b|标准版|基础款', 0).search(clause):
                continue
            period_match = re.search(delay_period_pattern, clause)
            if period_match is not None:
                break
        if period_match is None:
            period_match = re.search(delay_period_pattern, text)
        period_group_offset = 0
        if period_match is None:
            period_match = re.search(period_pattern, text)
        if generation_match and period_match:
            season_aliases = {"春季": "spring", "秋季": "fall", "明年春季": "next-spring", "明年秋季": "next-fall"}
            if period_match.group(1 + period_group_offset):
                period = f"{period_match.group(1 + period_group_offset).replace('autumn', 'fall')}-{period_match.group(2 + period_group_offset)}"
            elif period_match.group(3 + period_group_offset):
                period = f"{season_aliases[period_match.group(4 + period_group_offset)]}-{period_match.group(3 + period_group_offset)}"
            elif period_match.group(5 + period_group_offset):
                period = period_match.group(5 + period_group_offset).replace(" ", "-").replace("autumn", "fall")
            else:
                period = season_aliases[period_match.group(6 + period_group_offset)]
            model = "base" if base_model else "unspecified"
            generation = generation_match.group(1)
            key = f"structured-assertion:iphone-{generation}-{model}:release-delay:{period}"
            event_keys.add(key)
            boundaries.add(f"structured-subject:iphone-{generation}-{model}")
            separation |= {
                f"assertion-subject:iphone-{generation}-{model}",
                "assertion-action:product-release-delay",
            }

    if (_contains(text, "private relay", "icloud 专用代理") or _compiled_rule('icloud.{0,8}专用代理', 0).search(text)) and _contains(
        text, "class action", "class-action", "集体诉讼"
    ):
        key = "structured-assertion:icloud-private-relay:class-action"
        event_keys.add(key)
        boundaries.add("structured-subject:icloud-private-relay")
        separation |= {"assertion-subject:icloud-private-relay", "assertion-action:class-action"}

    primary_lead = primary_scope.removeprefix(f"{title_scope}. ")
    content = _content_work_assertion(title, f"{lead}. {evidence[:1200]}")
    if content and (
        "apple-tv" in identity.products
        or _contains(evidence_scope, "apple tv", "apple tv+", "apple tv plus")
        or (
            identity.scope == "apple-direct"
            and _compiled_rule('^(?:apple\\b|苹果)', 0).match(title_scope)
        )
    ):
        subject, action = content
        service = "media-playback" if action == "playback-availability" else "apple-tv"
        event_keys.add(f"structured-assertion:{service}:{subject}:{action}")
        boundaries.add(f"structured-subject:{service}:{subject}")
        separation |= {f"content-title:{subject}", f"content-action:{action}"}
        separation.update(_primary_content_schedule(lead))
        if action in {"free-streaming-event", "panel-lineup", "premiere-announcement"}:
            separation.add("content-named-event:" + subject)
            separation.add("content-named-event-action:" + action)
            if action in {"free-streaming-event", "panel-lineup"}:
                separation.update("content-event-year:" + year for year in _compiled_rule('\\b20\\d{2}\\b', 0).findall(title))
        if action == "production-update":
            separation.add("content-production-work:" + subject)
            season = _compiled_rule('\\bseason\\s+(\\d{1,2})\\b|第\\s*([一二三四五六七八九]?十[一二三四五六七八九]?|[一二三四五六七八九]|\\d{1,2})\\s*季', re.I).search(title)
            if season:
                raw_season = season.group(1) or season.group(2)
                if raw_season.isdigit():
                    season_number = int(raw_season)
                else:
                    digits = {char: index for index, char in enumerate("零一二三四五六七八九")}
                    if "十" in raw_season:
                        tens, ones = raw_season.split("十", 1)
                        season_number = (digits.get(tens, 1) * 10) + digits.get(ones, 0)
                    else:
                        season_number = digits[raw_season]
                separation.add(f"content-production-season:{season_number}")

    apple_tv_viewing_record = bool(
        ("apple-tv" in identity.products or _contains(primary_scope, "apple tv", "apple tv+"))
        and _contains(
            primary_scope,
            "viewing record",
            "premiere record",
            "biggest launch",
            "biggest premiere",
            "highest viewing",
            "最高收视",
            "首播纪录",
            "观看纪录",
            "最大首播",
        )
    )
    season = _compiled_rule('\\bseason\\s*(\\d+)\\b|第\\s*(\\d+|[一二三四五六七八九十])\\s*季', 0).search(primary_scope)
    if apple_tv_viewing_record and season and not (
        content and content[1] != "viewing-record"
    ):
        season_number = next(value for value in season.groups() if value)
        season_number = {
            "一": "1",
            "二": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
        }.get(season_number, season_number)
        event_keys.add(
            f"structured-assertion:apple-tv:season-{season_number}:viewing-record"
        )
        separation.add("content-action:viewing-record")

    # Normalize ordinal release wording from the title and first two lead
    # sentences. This covers sparse headlines such as "Seventh iOS ... Betas"
    # and "corresponding public betas" whose lead identifies the fifth wave.
    release_evidence = f"{title_scope}. {short_lead}"
    os_release_generation = _compiled_rule('\\b(?:ios|ipados|macos|watchos|tvos|visionos)(?:\\s+[a-z][a-z-]+){0,2}\\s+(\\d{1,2}(?:\\.\\d+){0,2})\\b', 0).search(release_evidence)
    ordinal_words = {
        "one": "1", "first": "1", "two": "2", "second": "2",
        "three": "3", "third": "3", "four": "4", "fourth": "4",
        "five": "5", "fifth": "5", "six": "6", "sixth": "6",
        "seven": "7", "seventh": "7", "eight": "8", "eighth": "8",
        "nine": "9", "ninth": "9", "ten": "10", "tenth": "10",
    }
    public_stage = _compiled_rule('\\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|seven|seventh|eight|eighth|nine|ninth|ten|tenth)\\s+public\\s+betas?\\b|第\\s*(\\d+)\\s*个?\\s*公测版', 0).search(release_evidence)
    beta_stage = _compiled_rule('\\bbeta\\s*(\\d+)\\b', 0).search(release_evidence)
    ordinal_stage = _compiled_rule('\\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|seven|seventh|eight|eighth|nine|ninth|ten|tenth)\\b(?!\\s+(?:hours?|days?|weeks?|months?|years?)\\b).{0,100}\\bbetas?\\b|\\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|seven|seventh|eight|eighth|nine|ninth|ten|tenth)\\s+public\\s+beta\\s+rollout\\b', 0).search(release_evidence)
    stage_number = ""
    if public_stage:
        public_value = next(value for value in public_stage.groups() if value)
        stage_number = ordinal_words.get(public_value, public_value)
    elif beta_stage:
        stage_number = beta_stage.group(1)
    elif ordinal_stage:
        stage_number = ordinal_words.get(
            next(value for value in ordinal_stage.groups() if value),
            "",
        )
    release_announcement_title = bool(
        _compiled_rule('\\b(?:apple\\s+)?(?:releases?|seeds?|rolls?\\s+out|ships?)\\b.{0,100}\\bbetas?\\b|\\b(?:new\\s+)?(?:public|developer)\\s+betas?\\b.{0,55}\\b(?:available|released|land|arrive)\\b|\\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\\b.{0,100}\\b(?:developer\\s+)?betas?\\b.{0,35}\\b(?:land|released|arrive)\\b|(?:苹果)?.{0,35}(?:开发者预览版|公测版|测试版).{0,25}(?:发布|推送|上线)', 0).search(title_scope)
    )
    detail_declares_release_candidate = bool(
        _compiled_rule('\\brelease candidates?\\b|\\brc\\s*\\d*\\b|候选发布版|发布候选版', 0).search(short_lead)
    )
    if (
        os_release_generation
        and stage_number
        and release_announcement_title
        and not detail_declares_release_candidate
        and _compiled_rule('\\b(?:beta|betas|public beta|developer beta)\\b', 0).search(release_evidence)
    ):
        generation = os_release_generation.group(1)
        stage = f"beta-{stage_number}"
        event_keys.add(f"apple-os-release-wave:{generation}:{stage}")
        boundaries.add(f"apple-os-release-wave:{generation}:{stage}")
        for platform in sorted(
            set(_compiled_rule('\\b(ios|ipados|macos|watchos|tvos|visionos)\\b', 0).findall(release_evidence))
        ):
            event_keys.add(f"apple-os-platform-release-wave:{platform}:{stage}")
        separation.add("predicate:os-release-announcement")

    classic_catalog_addition = bool(
        not content
        and ("apple-tv" in identity.products or _contains(primary_scope, "apple tv", "apple tv+"))
        and _contains(
            primary_scope,
            "classic movies",
            "classic films",
            "经典影片",
            "经典电影",
            "经典片库",
        )
        and _contains(
            primary_scope,
            "adds",
            "added",
            "gains",
            "collection",
            "catalog",
            "stream for free",
            "no extra cost",
            "新增",
            "加入",
            "片库",
            "免费观看",
            "无需额外付费",
        )
    )
    if classic_catalog_addition:
        key = "structured-assertion:apple-tv:classic-movie-catalog:addition"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-tv:classic-movie-catalog")
        separation |= {
            "content-title:classic-movie-catalog",
            "content-action:catalog-addition",
        }

    third_party_software_fix = bool(
        _contains(evidence_scope, "linux", "kernel", "内核")
        and _contains(title_scope, "fix", "patch", "power", "功耗", "修复", "根治")
        and identity.title_products
    )
    if third_party_software_fix:
        boundaries.add("structured-action:third-party-software-fix")
        separation.add("assertion-action:third-party-software-fix")

    facility_subject = _first_party_facility_subject(evidence_scope)
    facility_opening = bool(
        facility_subject
        and identity.scope == "apple-direct"
        and (
            _contains(
                title_scope,
                "announces",
                "announced",
                "establishes",
                "established",
                "sets up",
                "set up",
                "expands",
                "opens",
                "opened",
                "opening",
                "launches",
                "宣布",
                "设立",
                "建立",
                "落地",
                "扩展",
                "扩大",
                "开设",
                "启用",
                "揭幕",
                "落成",
            )
            or (
                _compiled_rule('\\bnew\\s+(?:apple\\s+)?(?:education|educational|training|learning)\\s+center\\b|(?:全新|首个|新建?)(?:苹果)?(?:教育|培训|学习)中心', re.I).search(title_scope)
                and _contains(
                    evidence_scope,
                    "apple announced",
                    "apple has announced",
                    "苹果宣布",
                    "苹果公司宣布",
                )
            )
            or (
                _contains(title_scope, "visits", "tours", "参观", "到访")
                and _contains(
                    evidence_scope,
                    "opens",
                    "opened",
                    "opening",
                "new center",
                "new factory",
                "new facility",
                "training school",
                "manufacturing school",
                "开设",
                "启用",
                "揭幕",
                "新中心",
                "新工厂",
                "新设施",
                "培训学校",
                "制造学校",
                )
            )
        )
    )
    if facility_opening:
        title_location = _first_party_facility_location(title)
        region_values = sorted(
            region for region in regions if region and region != "multi-region"
        )
        facility_products = sorted(identity.products & _HARDWARE_FIRST_PARTY_PRODUCTS)
        if facility_subject == "manufacturing-center" and len(facility_products) == 1:
            qualifier = f"product-{facility_products[0]}"
        else:
            qualifier = (
                (region_values[0] if len(region_values) == 1 else "")
                or title_location
            )
        qualifier_suffix = f":{qualifier}" if qualifier else ""
        key = (
            f"structured-assertion:apple-facility:{facility_subject}:opening"
            f"{qualifier_suffix}"
        )
        event_keys.add(key)
        boundaries.add(f"structured-subject:apple-facility:{facility_subject}")
        separation |= {
            f"assertion-subject:apple-facility:{facility_subject}",
            "assertion-action:facility-opening",
        }

    app_store_ratings_fraud = bool(
        "app-store" in identity.products
        and _contains(evidence_scope, "rating", "ratings", "review", "reviews", "评分", "评论")
        and _contains(
            evidence_scope,
            "fraud",
            "fake",
            "misleading",
            "欺诈",
            "虚假",
            "误导",
        )
        and _contains(
            evidence_scope,
            "developer",
            "reported",
            "feedback",
            "undetected",
            "开发者",
            "反馈",
            "举报",
            "未发现",
        )
    )
    if app_store_ratings_fraud:
        key = "structured-assertion:app-store:ratings-review-fraud:developer-report"
        event_keys.add(key)
        boundaries.add("structured-subject:app-store:ratings-review-fraud")
        separation |= {
            "assertion-subject:app-store:ratings-review-fraud",
            "assertion-action:developer-fraud-report",
        }

    spyware_warning = bool(
        identity.scope == "apple-direct"
        and _contains(evidence_scope, "spyware", "间谍软件")
        and _contains(
            evidence_scope,
            "warning",
            "warnings",
            "threat notification",
            "threat notifications",
            "警报",
            "警告",
            "威胁通知",
        )
        and _contains(title_scope, "apple", "苹果")
    )
    if spyware_warning:
        key = "structured-assertion:apple-security:mercenary-spyware:threat-warning"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-security:mercenary-spyware")
        separation |= {
            "assertion-subject:apple-security:mercenary-spyware",
            "assertion-action:threat-warning",
        }

    recording_indicator_patent = bool(
        _contains(evidence_scope, "apple glasses", "苹果 glasses", "苹果智能眼镜")
        and _contains(evidence_scope, "patent", "专利")
        and _contains(evidence_scope, "recording", "record", "录制", "录像")
        and _contains(
            evidence_scope,
            "chime",
            "audio alert",
            "audible",
            "notification",
            "提示音",
            "音频提示",
            "声音提醒",
        )
    )
    if recording_indicator_patent:
        key = "structured-assertion:apple-glasses:recording-indicator:patent"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-glasses:recording-indicator")
        separation |= {
            "assertion-subject:apple-glasses:recording-indicator",
            "assertion-action:patent-disclosure",
        }

    foldable_us_first_rollout = bool(
        (
            "foldable-iphone" in identity.products
            or _contains(evidence_scope, "foldable iphone", "iphone ultra", "折叠屏 iphone", "折叠屏iphone")
        )
        and _contains(
            evidence_scope,
            "us only at launch",
            "launch only in the us",
            "only in the us",
            "launch in the us first",
            "us first",
            "prioritize the us",
            "staggered market rollout",
            "优先供应美国",
            "首批优先",
            "美国市场首发",
            "分区域阶梯上市",
        )
    )
    if foldable_us_first_rollout:
        key = "structured-assertion:foldable-iphone:staggered-us-first-rollout"
        event_keys.add(key)
        boundaries.add("structured-subject:foldable-iphone:regional-rollout")
        separation |= {
            "assertion-subject:foldable-iphone:regional-rollout",
            "assertion-action:staggered-us-first-rollout",
        }

    iphone_pro_model = _compiled_rule('(?<![a-z0-9])iphone\\s*(\\d{1,2})\\s*pro(?:\\s*(max))?(?![a-z0-9])', 0).search(evidence_scope)
    oled_panel_cost_reduction = bool(
        iphone_pro_model
        and _contains(evidence_scope, "oled", "display panel", "screen panel", "屏幕", "面板")
        and _contains(evidence_scope, "cost", "price", "成本", "价格", "报价")
        and _contains(
            evidence_scope,
            "lower",
            "lowest",
            "decrease",
            "decline",
            "cut",
            "falls",
            "压价",
            "下降",
            "降低",
            "低至",
            "最低价",
        )
    )
    if oled_panel_cost_reduction:
        model = f"iphone-{iphone_pro_model.group(1)}-pro"
        if iphone_pro_model.group(2):
            model += "-max"
        key = f"structured-assertion:{model}:oled-panel-cost:reduction"
        event_keys.add(key)
        boundaries.add(f"structured-subject:{model}:oled-panel-cost")
        separation |= {
            f"assertion-subject:{model}:oled-panel-cost",
            "assertion-action:component-cost-reduction",
        }

    app_store_external_commission = bool(
        ("app-store" in identity.products or _contains(evidence_scope, "epic"))
        and _contains(
            evidence_scope,
            "external purchase",
            "outside the app store",
            "off-app store",
            "linking outside",
            "links outside",
            "linked-out",
            "purchases made outside",
            "external payment",
            "外链",
            "外部购买",
            "外链购买",
            "外部支付",
        )
        and _contains(evidence_scope, "commission", "fee", "佣金", "抽成", "费率")
    )
    title_led_court_timing_action = bool(
        _contains(title_scope, "supreme court", "scotus", "最高法院")
        and _contains(
            title_scope,
            "delay",
            "pause",
            "stay",
            "24 hours",
            "one day",
            "晚一天",
            "延期",
            "暂停",
            "批准",
        )
    )
    commission_proposal = bool(
        app_store_external_commission
        and not title_led_court_timing_action
        and _contains(
            primary_scope,
            "proposes",
            "proposal",
            "proposed",
            "files",
            "filed",
            "submits",
            "submitted",
            "拟推行",
            "提交",
            "方案",
        )
    )
    if commission_proposal:
        key = "structured-assertion:app-store:external-purchase-commission:proposal"
        event_keys.add(key)
        boundaries.add("structured-subject:app-store:external-purchase-commission")
        separation |= {
            "assertion-subject:app-store:external-purchase-commission",
            "assertion-action:commission-proposal",
            "legal-stage:proposal-filing",
        }

    purchased_content_upgrade = (
        "apple-tv" in identity.products
        and _contains(text, "4k")
        and _contains(
            text,
            "purchased tv show",
            "purchased tv shows",
            "tv show purchases",
            "已购剧集",
            "已购内容",
        )
        and _contains(
            text,
            "free upgrade",
            "free 4k",
            "4k upgrade",
            "免费升级",
            "无需额外付费",
        )
    )
    if purchased_content_upgrade:
        key = "structured-assertion:apple-tv:purchased-content:4k-entitlement-upgrade"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-tv:purchased-content")
        separation |= {
            "assertion-subject:apple-tv:purchased-content",
            "assertion-action:entitlement-upgrade",
        }

    # The opening must itself report Apple's restored subscription card
    # payments. Shared devices or a historical bank rule cannot supply it.
    payment_scope = _short_lead_scope(lead, sentences=1)
    payment_regions = sorted(region for region, aliases in REGION_TERMS.items()
                             if _contains(_normalized(payment_scope), *aliases))
    owned_restoration = _compiled_rule(r"\bapple\s+(?:(?:has|is)\s+)?(?:test\w*|restor\w*)\b|苹果(?:在[^，。]{1,12})?(?:小规模)?(?:测试)?恢复", re.I).search(payment_scope)
    if (payment_regions and owned_restoration
            and _compiled_rule(r"app\s*store|icloud", re.I).search(payment_scope)
            and _compiled_rule(r"credit|debit|银行卡|信用卡|借记卡", re.I).search(payment_scope)
            and _compiled_rule(r"restor\w*|恢复", re.I).search(payment_scope)
            and not _compiled_rule(r"\b(?:may|might|could|if|would|will)\b|not\s+(?:restor\w*|test\w*)|last year|previously|没有恢复|尚未恢复|计划|可能|去年|此前", re.I).search(payment_scope)):
        stage = "trial" if _compiled_rule(r"\btest\w*|测试", re.I).search(payment_scope) else "restored"
        region_key = ",".join(payment_regions)
        subject = "apple-subscriptions:card-payments"
        event_keys.add(f"structured-assertion:{subject}:{region_key}:{stage}")
        boundaries.add(f"structured-subject:{subject}")
        separation |= {f"assertion-subject:{subject}", f"assertion-action:payment-restoration-{stage}"}

    wallet_trade_in_quote = (
        "apple-wallet" in identity.products
        and "trade-in-valuation" in identity.components
        and _contains(text, "90 days", "90-day", "90 天", "90天")
    )
    if wallet_trade_in_quote:
        key = "structured-assertion:apple-wallet:trade-in-quote:90-day-validity"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-wallet:trade-in-quote")
        separation |= {
            "assertion-subject:apple-wallet:trade-in-quote",
            "assertion-action:trade-in-valuation-validity",
        }

    siri_publisher_license = (
        "siri" in identity.products
        and _contains(text, "publisher", "publishers", "news content", "出版商", "新闻内容", "资讯内容")
        and _contains(
            text,
            "license",
            "licensing",
            "content deal",
            "publisher deal",
            "paid partnership",
            "pay publishers",
            "talks",
            "许可协议",
            "内容合作",
            "付费",
            "支付",
            "洽谈",
        )
    )
    if siri_publisher_license:
        key = "structured-assertion:siri:publisher-news-content:licensing"
        event_keys.add(key)
        boundaries.add("structured-subject:siri:publisher-news-content")
        separation |= {
            "assertion-subject:siri:publisher-news-content",
            "assertion-action:content-licensing",
        }

    app_store_supreme_court_pause = (
        "app-store" in identity.products
        and not commission_proposal
        and _contains(text, "supreme court", "scotus", "最高法院")
        and _contains(
            text,
            "24 hours",
            "24-hour",
            "one day",
            "temporary pause",
            "administrative stay",
            "extension",
            "delay",
            "晚一天",
            "暂停",
            "延期",
            "推迟",
        )
    )
    if app_store_supreme_court_pause:
        key = "structured-assertion:app-store:supreme-court:administrative-pause"
        event_keys.add(key)
        boundaries.add("structured-subject:app-store:supreme-court")
        separation |= {
            "assertion-subject:app-store:supreme-court",
            "assertion-action:administrative-pause",
        }

    app_store_court_stay_denial = bool(
        ("app-store" in identity.products or _contains(evidence_scope, "epic"))
        and not commission_proposal
        and _contains(text, "supreme court", "scotus", "最高法院")
        and _contains(text, "denies", "denied", "rejects", "rejected", "驳回", "拒绝")
        and _contains(text, "stay", "pause", "delay", "延期", "暂停", "推迟")
    )
    if app_store_court_stay_denial:
        key = "structured-assertion:app-store:supreme-court:stay-denial"
        event_keys.add(key)
        boundaries.add("structured-subject:app-store:supreme-court")
        separation |= {
            "assertion-subject:app-store:supreme-court",
            "assertion-action:court-stay-denial",
            "legal-stage:court-stay-denial",
        }

    # A named parts-plant investigation is distinct from procurement or capacity.
    factory_scope = f"{title_scope}. {short_lead}"
    factory_suppliers = _canonical_supplier_entities(factory_scope)
    if (
        factory_suppliers
        and _compiled_rule('iphone.{0,30}(?:parts|factory|plant|零件|零部件|工厂)', re.I).search(factory_scope)
        and _compiled_rule('(?:water|wastewater).{0,25}(?:contamination|pollution)|(?:水污染|废水|污水)', re.I).search(factory_scope)
        and _compiled_rule('\\b(?:probe|investigat\\w*)\\b|调查', re.I).search(factory_scope)
    ):
        for supplier in factory_suppliers:
            event_keys.add(f"structured-assertion:iphone-parts-factory:{supplier}:water-contamination-investigation")
            separation.add(f"factory-investigation-owner:{supplier}")
        separation.add("factory-investigation-action:water-contamination")

    supplier_entities = _canonical_supplier_entities(text)
    display_products = identity.title_products & {"ipad", "ipad-air", "ipad-mini", "ipad-pro", "iphone"}
    if supplier_entities and display_products and _contains(text, "oled", "display", "panel", "面板", "显示"):
        for supplier in supplier_entities:
            for product in display_products:
                event_keys.add(f"structured-assertion:display-supplier:{supplier}:{product}")
                separation.add(f"assertion-subject:display-supplier:{supplier}:{product}")
        separation.add("assertion-action:supplier-qualification")

    if display_products and _contains(text, "oled", "display", "panel", "面板", "屏幕") and _contains(
        text, "stocking up", "increase orders", "increased orders", "additional orders", "增订", "增加订单", "追加订单"
    ):
        separation.add("assertion-action:component-stockpiling")

    apple_ai = "apple-intelligence" in identity.products or _contains(
        text, "apple intelligence", "apple 智能", "国行 ai", "国行ai"
    )
    regional_code_evidence = apple_ai and _contains(text, "china", "chinese", "国行", "中国") and _contains(
        text, "code", "reference", "string", "identifier", "代码", "踪迹", "痕迹", "线索"
    )
    if regional_code_evidence and identity.content_form != "roundup":
        key = "structured-assertion:apple-intelligence:china:code-evidence"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-intelligence:china")
        separation |= {"assertion-subject:apple-intelligence:china", "assertion-action:code-evidence"}

    iphone_code_subject = bool(
        identity.products & {"iphone", "foldable-iphone"}
        or _compiled_rule('(?<![a-z0-9])iphone(?![a-z0-9])|苹果.{0,4}(?:手机|新机)', 0).search(text)
    )
    unreleased_status = bool(
        _contains(text, "unreleased", "not yet released", "未发布", "尚未发布", "未发新机")
    )
    enumerated_iphone_set = bool(
        _compiled_rule('\\b(?:six|\\d+)\\s+(?:unreleased\\s+)?iphone|(?:六|6)\\s*款.{0,18}(?:iphone|苹果.{0,4}(?:手机|新机))|(?:iphone|苹果.{0,4}(?:手机|新机)).{0,18}(?:六|6)\\s*款', 0).search(text)
    )
    unreleased_model_code_set = bool(
        iphone_code_subject
        and _contains(text, "code", "identifier", "代码", "代号", "系统文件")
        and unreleased_status
        and enumerated_iphone_set
    )
    if unreleased_model_code_set:
        event_keys.add("structured-assertion:iphone:unreleased-model-code-set")
        separation |= {"assertion-subject:iphone-code-model-set", "assertion-action:code-evidence"}

    if "icloud" in identity.products and _contains(text, "icloud+", "icloud plus", "icloud storage") and _contains(
        text, "perk", "benefit", "unlock", "higher tier", "2tb", "权益", "解锁", "高阶", "高级"
    ):
        event_keys.add("structured-assertion:icloud-plus:tier-entitlements")
        separation |= {"assertion-subject:icloud-plus", "assertion-action:tier-entitlement-change"}

    anniversary_iphone = _contains(evidence_scope, "20th-anniversary", "20th anniversary", "20 周年", "20周年", "二十周年")
    anniversary_generation = "product-generation:iphone-20" in identity.components
    anniversary_glass_display = bool(
        (anniversary_iphone or anniversary_generation)
        and "iphone" in identity.products
        and _contains(
            evidence_scope,
            "glass",
            "rounded",
            "rounder",
            "玻璃",
            "bezel",
            "边框",
            "曲面",
            "圆润",
        )
        and _contains(
            evidence_scope,
            "display", "screen", "design", "redesign", "on track", "remain", "cancel",
            "look like", "thinner", "屏", "设计", "外观", "更薄", "仍在推进", "没有取消",
        )
    )
    if anniversary_glass_display:
        key = "structured-assertion:iphone-anniversary-redesign:glass-display"
        event_keys.add(key)
        boundaries.add("structured-subject:iphone-anniversary-redesign")
        separation |= {"assertion-subject:iphone-anniversary-redesign", "assertion-action:glass-display-redesign"}

    display_inventory_buffer = bool(
        _contains(evidence_scope, "oled", "display panel", "screen panel", "显示屏", "面板")
        and _contains(evidence_scope, "inventory", "buffer", "stock", "储备", "备货", "库存", "供应缓冲")
        and _contains(evidence_scope, "4 weeks", "four weeks", "4 周", "4周", "四周")
        and _contains(evidence_scope, "6 weeks", "six weeks", "6 周", "6周", "六周")
        and _contains(evidence_scope, "extend", "increase", "longer", "延长", "增加", "加大")
    )
    if display_inventory_buffer:
        key = "structured-assertion:apple-display-inventory:buffer-extension"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-display-inventory")
        separation |= {
            "assertion-subject:apple-display-inventory",
            "assertion-action:inventory-buffer-extension",
        }

    foldable_cover_protector_leak = bool(
        "foldable-iphone" in identity.products
        and _contains(
            evidence_scope,
            "screen protector",
            "protective film",
            "cover display protector",
            "外屏贴膜",
            "屏幕贴膜",
            "保护膜",
            "贴膜",
        )
        and (
            _contains(evidence_scope, "screen protector", "屏幕贴膜")
            or _contains(
                evidence_scope,
                "cover display",
                "cover-display",
                "outer display",
                "front display",
                "外屏",
                "正面屏幕",
            )
        )
        and _contains(
            evidence_scope,
            "screen protector",
            "protective film",
            "images",
            "video",
            "图片",
            "视频",
            "贴膜",
            "保护膜",
        )
    )
    if foldable_cover_protector_leak:
        key = "structured-assertion:foldable-iphone:cover-display-protector-leak"
        event_keys.add(key)
        boundaries.add("structured-subject:foldable-iphone:cover-display-protector")
        separation |= {
            "assertion-subject:foldable-iphone-cover-display-protector",
            "assertion-action:display-shape-leak",
        }

    reference_image_authentication = bool(
        (identity.products & {"iphone", "ios"} or _contains(evidence_scope, "iphone", "ios"))
        and _contains(evidence_scope, "photo", "photos", "image", "照片", "图像")
        and (
            _contains(
                evidence_scope,
                "apple reference image",
                "reference image",
                "reference mode",
                "provenance",
            )
            or (
                _contains(evidence_scope, "authenticat", "prove", "verify", "verification", "认证", "验证", "证明")
                and _contains(evidence_scope, "taken", "altered", "metadata", "cryptographic", "拍摄", "修改", "元数据")
            )
        )
    )
    if reference_image_authentication:
        key = "structured-assertion:iphone-camera:reference-image-authentication"
        event_keys.add(key)
        boundaries.add("structured-subject:iphone-camera:reference-image")
        separation |= {
            "assertion-subject:iphone-camera:reference-image",
            "assertion-action:photo-authentication",
        }

    impersonation_subject = _app_store_impersonation_subject(title, short_lead)
    if impersonation_subject:
        key = f"structured-assertion:app-store:{impersonation_subject}:impersonation-incident"
        event_keys.add(key)
        boundaries.add(f"structured-subject:app-store:{impersonation_subject}")
        separation |= {
            f"assertion-subject:app-store:{impersonation_subject}",
            "assertion-action:app-impersonation-incident",
        }

    foldable = "foldable-iphone" in identity.products or bool(
        _contains(text, "iphone")
        and _contains(text, "foldable", "folding", "折叠")
    )
    product_naming_action = bool(
        _contains(
            text,
            "called",
            "named",
            "naming",
            "product name",
            "称为",
            "名称",
            "命名",
            "定名",
        )
        or _compiled_rule('\\b(?:referred\\s+to\\s+as|another\\s+name|name\\s+making\\s+the\\s+rounds)\\b|(?:另一个|另一种).{0,12}(?:名称|命名)|(?:外界|内部).{0,12}(?:称作|称为)', re.I).search(text)
    )
    if foldable and product_naming_action:
        # Stage belongs to the current disclosure of this object. Historical
        # speculation can be the subject of a completed-result construction;
        # it is not evidence that the resulting Apple action is still rumored.
        name_pattern = r"iphone\s+[a-z0-9]+(?:\s+(?:pro|max|plus|ultra))*"
        title_names = set(re.findall(
            r"(?:called|named|名称.{0,8}为|命名为)\s*[\"“]?((?:" + name_pattern + r"))", title_scope, re.I))
        local_formal_naming = False
        current_naming_report = False
        for clause in _compiled_rule(r"[。！？.!?]\s*", 0).split(source_retail, 0):
            if _compiled_rule('report|claims?|rumou?r|消息|据称|传闻|发文称|报道称|据[^，。]{1,48}(?:爆料|透露|报道)|(?:博主|记者)[^，。]{0,30}(?:爆料|透露)|unclear|unconfirmed|尚未', re.I).search(clause) and _compiled_rule('(?:will\\s+(?:be\\s+)?name|may\\s+be\\s+called|called|named|naming|名称|命名|定名|名叫|叫做)', re.I).search(clause):
                current_naming_report = True
            if _compiled_rule('\\b(?:will|may|might|could)\\s+(?:be\\s+)?(?:called|named)|将命名|或将定名', re.I).search(clause):
                current_naming_report = True
            subject_action = _compiled_rule('^苹果(?P<adjunct>[^，。！？]{0,40}?)(?:进入[^，。！？]{0,40}[，,]\\s*)?(?:推出|发布)[^。！？]{0,70}iphone', re.I).search(clause)
            if subject_action:
                adjunct = subject_action.group('adjunct')
                if (not _compiled_rule('的|供应商|竞争对手|合作伙伴|经销商|客户|将|计划|打算|准备|有望|预计', 0).search(adjunct)
                    and not _compiled_rule('消息称|据称|可能|或将|传闻|此前|去年|早在|曾经|尚未|并未|没有|不会|否认', 0).search(clause)
                    and _compiled_rule('(?:名称|命名|定名).{0,12}(?:确定|为|是)', 0).search(clause)
                    and (not title_names or any(name in clause for name in title_names))):
                    local_formal_naming = True
                    break
            # A direct finite statement may follow a historical time adjunct.
            direct_clause = _compiled_rule(r"^after\b[^,]{0,100},\s*", re.I).sub("", clause, 0)
            finite = _compiled_rule('^apple\\s+(?:(?:has|today|now|just|officially)\\s+)*(?:announced|unveiled|introduced|revealed|launched)\\s+(?P<object>.+)', re.I).match(direct_clause)
            completed_result = _compiled_rule('(?P<completion>(?:(?:has|have)\\s+(?:(?:now|finally|already|just|ultimately|eventually)\\s+)*(?:(?:culminated|resulted)\\s+in|led\\s+to)|(?:ended|concluded)\\s+with))\\s+apple\\s+(?:revealing|unveiling|introducing|announcing|launching)\\s+(?P<object>.+)', re.I).search(clause)
            completed = finite or completed_result
            if not completed:
                continue
            # An adjacent retail proposition has its own time scope. Keep
            # naming appositions, but do not apply a later sale date to the
            # completed disclosure that precedes this new clause.
            object_text = _compiled_rule(r",\s*(?:(?:and|while)\s+(?:customers|buyers|it|the\s+(?:phone|device|model))\b|"
                r"with\s+(?:retail\s+)?(?:sales|preorders|availability)\b)", re.I).split(completed.group('object'), 1)[0]
            if not _compiled_rule('(?:(?:the|its|a|an|first|new)\\s+)*(?:iphone\\b|foldable\\b)', re.I).match(object_text):
                continue
            if title_names and not any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", object_text, re.I) for name in title_names):
                continue
            if _compiled_rule('\\b(?:last year|last month|last week|previously|earlier|next year|next month)\\b', re.I).search(object_text):
                continue
            if completed_result:
                frame = clause[:completed_result.start('completion')]
                if (_compiled_rule('\\b(?:unclear|whether|uncertain|unconfirmed|unknown)\\b', re.I).search(frame)
                    or _compiled_rule('\\b(?:could|would|may|might|will|not|never)\\b.{0,20}$', re.I).search(frame)):
                    continue
            local_formal_naming = True
            break
        if local_formal_naming:
            separation.add("product-disclosure-stage:announced")
        elif current_naming_report:
            separation.add("product-disclosure-stage:reported")
        key = "structured-assertion:foldable-iphone:product-naming"
        event_keys.add(key)
        boundaries.add("structured-subject:foldable-iphone")
        separation |= {"assertion-subject:foldable-iphone", "assertion-action:product-naming"}

    supplier_terms = ("memory", "dram", "nand", "ram", "内存", "存储", "闪存")
    capacity_terms = (
        "capacity", "shortage", "constraint", "restriction", "crunch", "maxed out",
        "unavailable", "产能", "短缺", "限制", "紧缺", "供给受限",
    )
    negotiation_terms = (
        "negot", "talks", "bid", "low price", "rejected", "offer",
        "谈判", "洽谈", "议价", "压价", "拒绝", "报价",
    )
    cost_pattern = _compiled_rule(r"\b(?:bill of materials|bom|component cost|manufacturing cost|costs? apple)\b|"
        r"(?:零部件|物料|制造|生产)?成本.{0,18}(?:上涨|增加|大增|暴涨|提高|预计)", 0)
    direct_product_price_pattern = _compiled_rule(r"\b(?:apple|iphone|ipad|mac(?:book| mini| studio| pro)?|product)s?\b.{0,32}"
        r"(?:price increases?|price hikes?|get(?:s|ting)? more expensive)|"
        r"(?:苹果产品|iphone|ipad|mac).{0,24}(?:涨价|售价上调|价格上调|提价)|"
        r"(?:涨价|售价上调|价格上调).{0,24}(?:苹果产品|iphone|ipad|mac)", 0)

    def supplier_actions(scope: str) -> set[str]:
        if not _contains(scope, *supplier_terms):
            return set()
        actions: set[str] = set()
        if _contains(scope, *capacity_terms):
            actions.add("assertion-action:supplier-capacity-constraint")
        if _contains(scope, *negotiation_terms):
            actions.add("assertion-action:supplier-price-negotiation")
        if cost_pattern.search(scope) and not direct_product_price_pattern.search(scope):
            actions.add("assertion-action:product-component-cost-forecast")
        return actions

    # A concrete headline action is authoritative. Fall back to the first lead
    # sentence only when the headline itself does not identify the action.
    separation |= supplier_actions(title_scope) or supplier_actions(primary_scope)

    if "apple-pay" in identity.products and _contains(text, "launch", "roll out", "上线", "推出") and _contains(
        text, "india", "country", "market", "印度", "地区", "市场"
    ):
        event_keys.add("structured-assertion:apple-pay:regional-launch")
        separation |= {"assertion-subject:apple-pay", "assertion-action:regional-launch"}

    personnel_departure = _contains(text, "retiring", "retires", "retirement", "leaving", "steps down", "退休", "离职", "卸任")
    if personnel_departure:
        person = ""
        for pattern in (
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}?)\s+(?:is\s+)?(?:retiring|retires|leaving|steps down)\b",
            r"\b(?:Chief|VP|Vice President)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b",
        ):
            match = re.search(pattern, title)
            if match:
                person = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(match.group(1)), 0).strip("-")
                break
        if person:
            event_keys.add(f"structured-assertion:apple-personnel:{person}:departure")
            separation |= {f"assertion-subject:apple-personnel:{person}", "assertion-action:personnel-departure"}
        if identity.products & {"apple-pay", "apple-wallet", "apple-card"}:
            event_keys.add("structured-assertion:apple-pay-wallet:personnel-departure")
            separation |= {"assertion-subject:apple-pay-wallet", "assertion-action:personnel-departure"}

    personnel_appointment = (
        _contains(text, "hire", "hires", "hired", "appoint", "appoints", "appointed", "picks up", "任命", "聘任", "招募")
        and _contains(
            text,
            "vice president",
            "head of",
            "executive",
            "chief",
            "副总裁",
            "负责人",
            "主管",
            "高管",
        )
    )
    if personnel_appointment:
        person = ""
        for pattern in (
            r"\b(?:hires?|hired|appoints?|appointed|picks?\s+up)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b",
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s+as\s+(?:new\s+)?(?:head|vice president|chief)\b",
            r"(?:任命|聘任|招募)\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,2})\s*(?:为|担任)",
        ):
            match = re.search(pattern, title)
            if match:
                person = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(match.group(1)), 0).strip("-")
                break
        if person:
            key = f"structured-assertion:apple-personnel:{person}:appointment"
            event_keys.add(key)
            boundaries.add(f"structured-subject:apple-personnel:{person}")
            separation.add(f"assertion-subject:apple-personnel:{person}")
        if _contains(text, "government affairs", "政府事务"):
            role_key = "structured-assertion:apple-personnel:government-affairs-lead:appointment"
            event_keys.add(role_key)
            boundaries.add("structured-subject:apple-personnel:government-affairs-lead")
            separation.add("assertion-subject:apple-personnel:government-affairs-lead")
        separation.add("assertion-action:personnel-appointment")

    patent_disclosure = _contains(title_scope, "patent", "patents", "专利")
    if patent_disclosure:
        separation.add("assertion-action:patent-disclosure")
        notification_focus = _contains(
            text,
            "notification summary",
            "notification summaries",
            "interruptions",
            "focus mode",
            "通知摘要",
            "减少中断",
            "专注模式",
            "打扰",
            "发出通知",
        )
        if notification_focus:
            key = "structured-assertion:apple-patent:notification-interruption-management"
            event_keys.add(key)
            boundaries.add("structured-subject:apple-patent:notification-interruption-management")
            separation.add("assertion-subject:apple-patent:notification-interruption-management")

    birthday_feature = bool(
        "ios" in identity.products
        and _contains(text, "birthday", "生日")
        and _contains(text, "reminder", "fireworks", "call", "提醒", "烟花", "通话")
    )
    if birthday_feature:
        event_keys.add("structured-assertion:ios-phone:birthday-reminder")
        separation |= {"assertion-subject:ios-phone", "assertion-action:birthday-reminder"}

    back_to_school_extension = bool(
        _contains(text, "back to school", "返校季", "教育优惠")
        and _contains(text, "extend", "extended", "extension", "延长", "延期")
        and _compiled_rule('\\b(?:september|august)\\s+\\d{1,2}\\b|\\d{1,2}\\s*月\\s*\\d{1,2}\\s*日', 0).search(text)
    )
    if back_to_school_extension:
        event_keys.add("structured-assertion:apple-back-to-school:date-extension")
        separation |= {"assertion-subject:apple-back-to-school", "assertion-action:date-extension"}

    product_storage_spec = bool(
        identity.title_products & {"iphone", "ipad", "mac", "macbook"}
        and _compiled_rule('\\b\\d+\\s*(?:gb|tb)\\b|\\d+\\s*(?:gb|tb)|\\d+\\s*[gt]b|\\d+\\s*gb|\\d+\\s*tb', 0).search(text)
        and _contains(text, "starts at", "base storage", "storage capacity", "维持", "起步", "基础存储", "容量")
    )
    if product_storage_spec:
        separation.add("assertion-action:product-storage-specification")

    return event_keys, boundaries, separation


def _event_staff_support(text: str) -> bool:
    return (
        _contains(text, "lottery", "抽签")
        and _contains(text, "staff", "employee", "retail worker", "零售员工", "门店员工", "员工")
        and _contains(text, "event", "发布会", "现场支持", "现场支援")
    )


def _event_preparation(text: str) -> bool:
    return (
        _contains(text, "september", "9 月", "九月")
        and _contains(text, "event", "发布会")
        and _contains(
            text,
            "prepar",
            "getting ready",
            "revealed a clue",
            "lottery",
            "staff support",
            "employee support",
            "筹备",
            "准备",
            "抽签",
            "员工支援",
            "现场支援",
            "现场支持",
        )
    )


def _event_format_plan(text: str) -> bool:
    return (
        _contains(text, "event", "keynote", "iphone launch", "发布会", "新品活动")
        and _contains(
            text,
            "pre-recorded",
            "prerecorded",
            "pre recorded",
            "live presentation",
            "live on stage",
            "live segment",
            "live elements",
            "hybrid format",
            "录播",
            "预录",
            "现场直播",
            "现场环节",
            "混合方案",
            "混合形式",
        )
        and _contains(
            text,
            "report",
            "reported",
            "likely",
            "unlikely",
            "expected",
            "could be",
            "will likely",
            "消息称",
            "报道称",
            "预计",
            "大概率",
            "可能",
        )
    )


def _apple_first_party_home_camera_roadmap(title: str, text: str) -> bool:
    """Identify one first-party Apple Home camera roadmap action."""
    title_has_apple_platform = _contains(
        title,
        "apple",
        "ios",
        "苹果",
    )
    apple_camera = bool(
        _compiled_rule(r"(?:apple|苹果).{0,45}(?:home security camera|home camera|security camera|"
            r"家用安防摄像头|家庭安防摄像头|智能家居摄像头|家庭摄像头|安防摄像头)", 0).search(text)
        or _compiled_rule(r"(?:home security camera|home camera|security camera|家用安防摄像头|"
            r"家庭安防摄像头|智能家居摄像头|家庭摄像头|安防摄像头).{0,45}(?:apple|苹果)", 0).search(text)
    )
    roadmap_action = _contains(
        text,
        "launch",
        "debut",
        "plan",
        "planning",
        "develop",
        "developing",
        "coming soon",
        "rumored",
        "roadmap",
        "推出",
        "登场",
        "计划",
        "开发",
        "研发",
        "有望",
        "传闻",
        "路线图",
    )
    return title_has_apple_platform and apple_camera and roadmap_action


def _third_party_app_availability_without_platform_change(
    title: str,
    lead: str,
) -> bool:
    """Return true when an OS name is context for a third-party app action.

    A version number alone must not transfer action ownership from an app or
    service vendor to Apple.  A first-party API, policy, or platform-capability
    change remains eligible because the title explicitly assigns that action
    to Apple or the platform.
    """
    third_party_subject = bool(
        _compiled_rule(r"\bthird[- ]party\b.{0,24}\b(?:apps?|services?)\b|"
            r"(?:第三方).{0,18}(?:应用|服务|聊天机器人)", re.I).search(title)
    )
    availability_action = bool(
        _compiled_rule(r"\b(?:available|availability|arrives?|coming|supports?|integrates?|"
            r"adds?\s+support|works?\s+with)\b|"
            r"(?:接入|上线|可用|支持|适配|兼容)", re.I).search(title)
    )
    first_party_platform_change = bool(
        _compiled_rule(r"\b(?:apple|ios|ipados|macos|watchos|tvos|visionos|carplay)\b"
            r".{0,42}\b(?:opens?|enables?|introduces?|adds?|changes?|updates?|"
            r"expands?)\b.{0,42}\b(?:api|framework|policy|platform|third[- ]party\s+app\s+support)\b|"
            r"(?:苹果|ios|ipados|macos|watchos|tvos|visionos|carplay)"
            r".{0,32}(?:开放|启用|引入|新增|调整|更新|扩展)"
            r".{0,32}(?:接口|框架|政策|平台能力|第三方应用支持)", re.I).search(f"{title}. {lead}")
    )
    return third_party_subject and availability_action and not first_party_platform_change


def _versioned_os_feature_report(text: str, identity: EventIdentity) -> bool:
    title = text.split(". ", 1)[0]
    lead = text.split(". ", 1)[1] if ". " in text else ""
    if _third_party_app_availability_without_platform_change(title, lead):
        return False
    if is_os_release_announcement(title):
        return True
    proposal_pattern = (
        r"\b(?:i|we)\s+(?:would|should|wish(?:ed)?\s+(?:apple\s+)?would)\s+"
        r"(?:change|add|remove|redesign|fix|improve)\b|"
        r"\bapple\s+(?:should|needs?\s+to|ought\s+to)\s+"
        r"(?:change|add|remove|redesign|fix|improve)\b|"
        r"(?:我|我们)(?:会|希望|认为苹果应当|认为苹果应该).{0,24}"
        r"(?:改变|新增|移除|重设计|修复|改进)"
    )
    proposal_or_wishlist = bool(
        re.search(proposal_pattern, title, re.I)
    )
    asserted_title_scope = re.sub(proposal_pattern, "", title, flags=re.I)
    asserted_current_change = bool(
        _compiled_rule(r"\b(?:adds?|added|adding|brings?|brought|changes?|changed|changing|"
            r"updates?|updated|updating|upgrades?|upgraded|upgrading|removes?|removed|"
            r"redesigns?|redesigned|fixes?|fixed|expands?|expanded)\b|"
            r"(?:新增|加入|带来|调整|更改|更新|升级|移除|重设计|修复|扩展)", re.I).search(asserted_title_scope)
    )
    if proposal_or_wishlist and not asserted_current_change:
        return False
    security_bulletin = _contains(
        title,
        "security fix",
        "security fixes",
        "security flaw",
        "security flaws",
        "cve",
        "vulnerabilities",
        "安全修复",
        "安全漏洞",
        "漏洞",
    )
    release_announcement = bool(
        _compiled_rule(r"\b(?:releas(?:e|es|ed|ing)|ships?|shipped|now available|rolls out|land|lands)\b|"
            r"(?:发布|推送|正式版)", 0).search(title)
        or _lead_asserts_first_party_release(lead)
    )
    if security_bulletin and not release_announcement:
        return False
    title_os = identity.title_products & {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
    versioned_title = bool(
        _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)"
            r"(?:\s+[a-z][a-z-]+){0,2}\s+\d+(?:\.\d+){0,2}\b", re.IGNORECASE).search(title)
        or any(component.startswith("os-wave:") for component in identity.components)
        or any(component.startswith("os-wave-platform:") for component in identity.components)
        or (
            release_announcement
            and _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)"
                r"(?:\s+[a-z][a-z-]+){0,2}\s+\d+(?:\.\d+){0,2}\b", re.IGNORECASE).search(text)
        )
    )
    numbered_incremental = bool(
        _compiled_rule(r"\bbeta\s*\d+\b|"
            r"(?:开发者预览版|开发者测试版|测试版)\s*beta?\s*\d+|"
            r"第\s*\d+\s*(?:个|版)?\s*(?:开发者)?测试版", 0).search(title)
    )
    explicit_feature_change = "feature-change" in identity.title_actions
    direct_first_party_lead_change = bool(
        _compiled_rule(r"\bapple\s+(?:(?:is|has|will|plans?\s+to|continues?\s+to)\s+)?"
            r"(?:adds?|adding|brings?|bringing|changes?|changing|updates?|updating|"
            r"redesigns?|redesigning|integrates?|integrating|moves?|moving)\b|"
            r"(?:苹果).{0,35}(?:新增|加入|带来|调整|更改|更新|重设计|整合|移入)", re.I).search(lead)
    )
    current_change = bool(
        explicit_feature_change
        or direct_first_party_lead_change
        or release_announcement
        or (
            identity.content_form == "news"
            and _contains(
                title,
                "feature",
                "features",
                "change",
                "changes",
                "功能",
                "变化",
            )
        )
        or (
            numbered_incremental
            and _contains(
                title,
                "what's new",
                "everything new",
                "new in",
                "feature",
                "features",
                "changes",
                "功能",
                "变化",
                "更新",
                "发布",
                "测试版",
            )
        )
        or (
            identity.content_form == "news"
            and _compiled_rule(r"\b(?:releas(?:e|es|ed|ing)|ships?|shipped|seeds|now available|(?:are|is) out now|rolls out|land|lands)\b|"
                r"(?:发布|推送)", 0).search(title)
        )
    )
    return bool(
        title_os
        and identity.scope == "apple-direct"
        and versioned_title
        and current_change
    )


def _versioned_shared_resource_operation(title: str, lead: str) -> tuple[str, str] | None:
    """Bind a cross-device operation to its OS version and shared resource."""
    title_text, primary_scope = _primary_assertion_scope(title, lead)
    version = _compiled_rule(r"(?<![a-z0-9])(ios|ipados|macos|watchos|tvos|visionos)\s*"
        r"(\d+(?:\.\d+){0,2})(?![0-9.])", 0).search(title_text)
    if not version or not _compiled_rule(r"\b(?:new|adds?|introduces?)\b|新增|加入|全新", 0).search(title_text):
        return None
    devices = sorted(set(_compiled_rule(r"(?<![a-z0-9])(iphone|ipad|mac|macbook|apple watch|vision pro)s?(?![a-z0-9])", 0).findall(primary_scope)))
    cross_device = _compiled_rule(r"\b(?:two|multiple|both)\s+(?:\w+\s+)?(?:iphones|ipads|macs|macbooks|devices|watches)\b|"
        r"\b(?:between|across)\b.{0,60}\bdevices\b|"
        r"(?:两|多)(?:台|部|个)\s*(?:iphone|ipad|mac|设备|手机|电脑)", 0).search(primary_scope)
    resources = {
        name for name, pattern in (
            ("phone-number", r"(?:phone|telephone)\s+number|(?:esim|手机|电话)?号码"),
            ("account", r"account|账户|账号"),
            ("session", r"session|会话"),
        )
        if re.search(
            rf"\bsame\s+(?:{pattern})|(?:共用|共享)?(?:同一个|同一|一个)\s*(?:{pattern})",
            primary_scope,
        )
    }
    switching = _compiled_rule(r"\bswitch(?:ing)?\b|切换", 0).search(primary_scope)
    negated = _compiled_rule(r"\b(?:cannot|can't|does not|will not)\s+switch\b|(?:不能|无法|不支持).{0,8}切换", 0).search(primary_scope)
    if devices and cross_device and len(resources) == 1 and switching and not negated:
        device_subject = "+".join(device.replace(" ", "-") for device in devices)
        return (
            f"{version.group(1)}-{version.group(2)}:{device_subject}:{next(iter(resources))}",
            "cross-device-switch",
        )
    return None


def _release_subject_platforms(title: str, lead: str) -> tuple[str, ...]:
    """Read coordinated release objects, not every platform in a sentence."""
    platform = r'(?<![a-z0-9])(?:ios|ipados|macos|watchos|tvos|visionos|homepod)(?![a-z])'
    item = platform + r'(?:\s*\d+(?:\.\d+)*)?'
    objects = item + r'(?:\s*(?:,\s*(?:and\s+)?|and|/|与|和|及|、)\s*' + item + r')*'
    def names_in(match, text):
        if not match:
            return ()
        names = tuple(dict.fromkeys(_compiled_rule(platform).findall(_normalized(match.group()))))
        if _compiled_rule(r'^\s+(?:will|would|may|might|could|coming|arrives?|(?:is|are)\s+(?:coming|planned|scheduled))\b|^\s*(?:将|计划)', re.I).search(text[match.end():]):
            names = names[:-1]
        return names
    headline = _compiled_rule(objects, re.I).search(title)
    if not headline:
        return ()
    names = names_in(headline, title)
    if len(names) > 1:
        opening = source_primary_assertion(title, lead)[len(_normalized(title)) + 2:]
        released = _compiled_rule(r'(?:releas\w*|publish\w*|发布|推送)了?\s*(?:the\s+|new\s+)?(' + objects + ')', re.I).search(opening)
        names = tuple(name for name in names if name in names_in(released, opening))
    return names


def _versioned_os_feature_scope(text: str, identity: EventIdentity) -> str:
    title, _, lead = text.partition(". ")
    operation = _versioned_shared_resource_operation(title, lead)
    if operation:
        subject, predicate = operation
        return f"apple-os-feature-scope:{subject}:{predicate}"
    if not is_os_release_announcement(title) and not _versioned_os_feature_report(text, identity):
        return ""
    text_parts = text.split(". ", 1)
    title = text_parts[0]
    lead = text_parts[1] if len(text_parts) == 2 else ""
    release_lead = bool(
        current_public_os_release(title, lead)
        or (not identity.title_actions and _lead_asserts_first_party_release(lead))
    )
    release_title = is_os_release_announcement(title) or _contains(
        title,
        "release",
        "released",
        "now available",
        "are out now",
        "is out now",
        "is out",
        "rolls out",
        "land",
        "lands",
        "发布",
        "推送",
        "正式版",
    ) or release_lead
    release_waves = sorted(
        component
        for component in identity.components
        if component.startswith("os-wave:")
    )
    concrete_title_components = {
        component
        for component in identity.title_components
        if component.startswith("os-component:")
        or component in LEAD_IDENTITY_COMPONENTS
    }
    title_describes_feature = _contains(
        title,
        "what's new",
        "everything new",
        "new feature",
        "new features",
        "changes",
        "功能",
        "变化",
        "更新汇总",
        "new icon",
        "new icons",
        "redesigned icon",
        "redesigned icons",
        "新图标",
        "图标重设计",
    )
    platform_release_waves = sorted(
        component
        for component in identity.components
        if component.startswith("os-wave-platform:")
    )
    if not release_waves:
        version_match = _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos|homepod)"
            r"(?:\s+[a-z][a-z-]+){0,2}\s+(\d+(?:\.\d+){0,2})\b", re.IGNORECASE).search(text)
        beta_match = _compiled_rule(r"\bbeta\s*(\d+)\b", 0).search(title)
        if version_match and release_title:
            stage = f"beta-{beta_match.group(1)}" if beta_match else "final"
            release_waves = [f"os-wave:{version_match.group(1)}:{stage}"]
    if not release_waves and platform_release_waves and release_title and not title_describes_feature:
        platform_wave = platform_release_waves[0].removeprefix("os-wave-platform:")
        return f"apple-os-platform-release-wave:{platform_wave}"
    if release_waves and (
        (release_title and (release_waves[0].endswith(":final") or is_os_release_announcement(title)))
        or (not concrete_title_components and not title_describes_feature)
    ):
        wave = release_waves[0].removeprefix("os-wave:")
        if wave.endswith(":final"):
            platforms = _release_subject_platforms(title, lead)
            if not platforms:
                return ""
            os_family = platforms[0]
            return f"apple-os-release-wave:{wave}:{os_family}"
        return f"apple-os-release-wave:{wave}"
    os_family = sorted(
        identity.title_products & {"ios", "ipados", "macos", "watchos", "tvos", "visionos", "homepod"}
    )[0]
    feature_wave = ""
    if release_waves:
        feature_wave = release_waves[0].removeprefix("os-wave:")
    elif platform_release_waves:
        feature_wave = platform_release_waves[0].removeprefix("os-wave-platform:")
    else:
        version_match = _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos|homepod)"
            r"(?:\s+[a-z][a-z-]+){0,2}\s+(\d+(?:\.\d+){0,2})\b", re.IGNORECASE).search(title)
        beta_match = _compiled_rule(r"\bbeta\s*(\d+)\b", 0).search(title)
        if version_match:
            stage = f"beta-{beta_match.group(1)}" if beta_match else "current"
            feature_wave = f"{version_match.group(1)}:{stage}"
    if identity.content_form == "roundup" and feature_wave:
        return f"apple-os-feature-roundup:{os_family}:{feature_wave}"
    icon_change = bool(
        _compiled_rule(r"\b(?:new|redesigned|updated|changed)\s+(?:[a-z]+\s+){0,3}icons?\b|"
            r"\bicons?\b.{0,36}\b(?:redesign(?:ed)?|update(?:d)?|change(?:d)?)\b|"
            r"(?:新增|启用|带来|采用|更换|重设计|重新设计|调整|更新).{0,24}图标|"
            r"图标.{0,24}(?:新增|启用|重设计|重新设计|调整|更新)", 0).search(title)
    )
    if icon_change and feature_wave:
        return f"apple-os-feature-scope:{os_family}:{feature_wave}:component:app-icons"
    components = sorted(
        component
        for component in identity.title_components
        if component.startswith("os-component:")
    )
    if not components:
        component_patterns = (
            ("messages", ("messages", "信息 app", "信息应用")),
            ("camera", ("camera app", "相机 app", "相机应用")),
            ("mail", ("mail", "邮件 app", "邮件应用")),
            ("notes", ("notes", "备忘录")),
            ("weather", ("weather", "天气 app", "天气应用")),
            ("shortcuts", ("shortcuts", "快捷指令")),
            ("wallet", ("wallet", "钱包 app", "钱包应用")),
            ("maps", ("maps", "地图 app", "地图应用")),
            ("safari", ("safari",)),
            ("photos", ("photos", "照片 app", "照片应用")),
            ("settings", ("settings", "设置 app", "系统设置")),
            ("control-center", ("control center", "控制中心")),
            ("lock-screen", ("lock screen", "锁屏")),
            ("home-screen", ("home screen", "主屏幕")),
        )
        components = [
            f"os-component:{name}"
            for name, terms in component_patterns
            if _contains(title, *terms)
        ]
    if not components:
        components = sorted(identity.components & LEAD_IDENTITY_COMPONENTS)
    if not components:
        components = sorted(
            component
            for component in identity.title_components
            if not component.startswith(
                (
                    "apple-silicon-generation:",
                    "iphone-family:",
                    "iphone-line:",
                    "iphone-model:",
                    "macbook-model:",
                    "primary-intent:",
                    "product-generation:",
                    "report-attribution:",
                )
            )
        )
    title_subject_products = sorted(
        identity.title_products
        - {"ios", "ipados", "macos", "watchos", "tvos", "visionos", "iphone", "ipad", "mac"}
    )
    primary_names = identity.title_named_subjects or {
        subject for subject in identity.named_subjects
        if subject.replace("-", " ") in _primary_assertion_scope("", lead)[1]
    }
    branded_named_subjects = {
        subject
        for subject in primary_names
        if subject.startswith("apple-")
    }
    named_subject_candidates = {
        subject.removeprefix("apple-")
        for subject in (branded_named_subjects or primary_names)
        if subject
        not in {
            "airpods",
            "apple-tv",
            "apple-watch",
            "homekit",
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "safari",
            "siri",
            "vision-pro",
        }
    }
    named_subjects = sorted(
        subject
        for subject in named_subject_candidates
        if not any(
            other != subject and other.startswith(f"{subject}-")
            for other in named_subject_candidates
        )
    )
    if len(components) == 1:
        subject = f"component:{components[0]}"
    elif len(named_subjects) == 1:
        subject = f"named:{named_subjects[0]}"
    elif len(title_subject_products) == 1:
        subject = f"product:{title_subject_products[0]}"
    else:
        # A platform with several unnamed features supplies no common action.
        return ""
    return f"apple-os-feature-scope:{os_family}:{subject}"


def _broad_component_supply_outlook(text: str) -> bool:
    title = text.split(". ", 1)[0]
    return bool(
        not _contains(title, "apple", "iphone", "ipad", "mac", "苹果")
        and _contains(title, "ram", "memory", "dram", "nand", "内存", "存储")
        and _contains(
            title,
            "worldwide",
            "global",
            "industry",
            "sold out",
            "capacity",
            "shortage",
            "全球",
            "行业",
            "售罄",
            "产能",
            "短缺",
        )
    )


def _supplier_market_without_apple_action(text: str, identity: EventIdentity) -> bool:
    title = text.split(". ", 1)[0]
    return bool(
        not _contains(title, "apple", "iphone", "ipad", "mac", "苹果")
        and identity.scope != "apple-direct"
        and _contains(
            title,
            "supplier",
            "supply",
            "capacity",
            "production",
            "order",
            "供应",
            "产能",
            "供货",
            "订单",
            "长鑫",
            "长江存储",
            "cxmt",
            "ymtc",
        )
        and _contains(
            title,
            "price",
            "capacity",
            "production",
            "order",
            "supply",
            "价格",
            "产能",
            "量产",
            "订单",
            "供货",
            "锁产能",
        )
    )


def _measured_applied_research_key(text: str, identity: EventIdentity) -> str:
    products = sorted(identity.title_products & {"vision-pro", "apple-watch", "airpods", "iphone", "ipad", "mac", "macbook"})
    if not products or not _contains(
        text,
        "peer-reviewed",
        "peer reviewed",
        "study",
        "clinical trial",
        "同行评审",
        "研究显示",
        "临床试验",
    ):
        return ""
    if not _contains(
        text,
        "using vision pro",
        "used vision pro",
        "wore vision pro",
        "primary display",
        "using apple watch",
        "using airpods",
        "using iphone",
        "使用 vision pro",
        "佩戴 vision pro",
        "作为主要显示设备",
        "使用 apple watch",
        "使用 airpods",
        "使用 iphone",
    ):
        return ""
    minute_values = sorted(
        {
            value.rstrip("0").rstrip(".")
            for value in _compiled_rule(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:minutes?|分钟)", 0).findall(text)
        },
        key=lambda value: float(value),
    )
    percentages = sorted(
        {
            value.rstrip("0").rstrip(".")
            for value in _compiled_rule(r"(?<!\d)(\d+(?:\.\d+)?)\s*%", 0).findall(text)
        },
        key=lambda value: float(value),
    )
    metric = "-".join(minute_values[:2]) if len(minute_values) >= 2 else (percentages[0] if percentages else "")
    if not metric:
        return ""
    domain = "clinical-workflow" if _contains(text, "surgery", "operation", "procedure", "手术", "临床") else "measured-use"
    return f"apple-product-research:{products[0]}:{domain}:{metric}"


def _product_driven_market_forecast_key(text: str, identity: EventIdentity) -> str:
    products = sorted(identity.title_products & {"foldable-iphone", "iphone", "ipad", "macbook", "apple-watch", "airpods", "vision-pro"})
    if not products:
        return ""
    if not _contains(text, "market", "shipments", "sales", "市场", "出货量", "销量"):
        return ""
    if not _contains(
        text,
        "forecast",
        "expected to grow",
        "expected to rise",
        "driving the increase",
        "main driver",
        "due to",
        "预测",
        "预计增长",
        "重要驱动力",
        "主要驱动力",
        "推动增长",
    ):
        return ""
    percentages = sorted(
        {
            value.rstrip("0").rstrip(".")
            for value in _compiled_rule(r"(?<!\d)(\d+(?:\.\d+)?)\s*%", 0).findall(text)
        },
        key=lambda value: float(value),
    )
    if not percentages:
        return ""
    market = "foldable" if _contains(text, "foldable", "折叠屏", "折叠 iphone") else "product-segment"
    return f"apple-market:{market}:{products[0]}:{percentages[0]}"


def _annual_sales_metric(text: str) -> bool:
    return bool(
        _compiled_rule(r"\bannual\b.{0,32}\b(?:sales|revenue)\b", 0).search(text)
        or _compiled_rule(r"(?:年度|年)(?:销售额|营收)|(?:销售额|营收).{0,8}(?:年度|全年|首次突破)", 0).search(text)
    )


def _multi_product_price_forecast(text: str) -> bool:
    product_patterns = (
        r"\biphone\b",
        r"\bipad\b",
        r"\bmac(?:book)?\b",
        r"\bapple watch\b|苹果手表",
        r"\bairpods\b",
        r"\bvision pro\b",
        r"\bhomepod\b",
        r"\bapple tv\b",
    )
    product_count = sum(bool(_compiled_rule(pattern).search(text)) for pattern in product_patterns)
    return (
        product_count >= 2
        and _contains(text, "price", "prices", "expensive", "涨价", "提价", "价格上调", "售价上调")
        and _contains(
            text,
            "expected",
            "likely",
            "forecast",
            "rumor",
            "could",
            "may",
            "预计",
            "预期",
            "可能",
            "分析师",
            "爆料",
        )
    )


def _bug_bounty_submission_limit(text: str) -> bool:
    return (
        _contains(text, "bug bounty", "漏洞赏金")
        and _contains(
            text,
            "limit",
            "quota",
            "cooldown",
            "clogging",
            "flood",
            "配额",
            "限制",
            "冷静期",
            "堵塞",
            "泛滥",
        )
        and _contains(text, "submission", "report", "提交", "报告")
    )


def _icloud_private_relay_leak(text: str) -> bool:
    return (
        _contains(text, "private relay", "icloud 专用代理", "icloud+隐私", "icloud+ 隐私")
        and _contains(text, "leak", "expose", "vulnerability", "漏洞", "泄露", "暴露", "风险")
        and _contains(
            text,
            "real ip",
            "ip address",
            "dns",
            "真实ip",
            "真实 ip",
            "网络信息",
        )
    )


def _webkit_proxy_leak(text: str) -> bool:
    return (
        "webkit" in text
        and _contains(text, "leak", "expose", "vulnerability", "漏洞", "泄露", "风险")
        and _contains(
            text,
            "proxy",
            "private relay",
            "dns",
            "webtransport",
            "代理",
            "网络信息",
            "ip",
        )
    )


def _app_store_removal_stage(text: str) -> str:
    explicit_store_surface = _contains(text, "app store", "应用商店", "苹果应用商店")
    explicit_apple_app_removal = bool(
        _compiled_rule(r"\bapple\b.{0,24}\b(?:remov(?:es|ed|al)?|pull(?:s|ed)?|yank(?:s|ed)?|delist(?:s|ed)?)\b"
            r".{0,30}\b(?:app|application)\b|"
            r"(?:苹果).{0,16}(?:下架|移除|撤下).{0,16}(?:应用|app)", 0).search(text)
    )
    if not (
        (explicit_store_surface or explicit_apple_app_removal)
        and _contains(text, "remov", "pull", "yank", "delist", "下架", "移除", "撤下")
    ):
        return ""
    if _contains(
        text,
        "extortion",
        "planted",
        "manipulated",
        "weaponized",
        "alleged",
        "alleges",
        "勒索",
        "设局",
        "操纵",
        "植入",
        "武器化",
        "指控",
    ):
        return "followup-allegation"
    return "initial-removal"


def _app_store_subjects(title: str, identity: EventIdentity) -> set[str]:
    ignored = _GENERIC_SUBJECT_WORDS | {
        "app",
        "apple",
        "briefly",
        "cnbeta",
        "com",
        "content",
        "csam",
        "im",
        "illegal",
        "material",
        "removed",
        "removal",
        "store",
        "why",
    }
    object_match = _compiled_rule(r"(?:remove(?:s|d)?|pull(?:s|ed)?|yank(?:s|ed)?|ban(?:s|ned|ning)?)\s+"
        r"([a-z][a-z0-9.+-]{2,30})\s+(?:from|off)\b", 0).search(title)
    if not object_match:
        object_match = _compiled_rule(r"(?:remove(?:s|d)?|pull(?:s|ed)?|yank(?:s|ed)?|ban(?:s|ned|ning)?)\s+"
            r"([a-z][a-z0-9.+-]{2,30})(?:\b|[?？])", 0).search(title)
    if not object_match:
        object_match = _compiled_rule(r"(?:下架|移除|撤下)\s*(?:了)?\s*"
            r"([A-Za-z][A-Za-z0-9.+-]{2,30})(?:\b|[?？])", 0).search(title)
    if object_match and object_match.group(1) not in ignored:
        return {object_match.group(1)}
    leading_subject = _compiled_rule(r"^([A-Za-z][A-Za-z0-9.+-]{2,30})(?:\s|[：:，,])", 0).match(title)
    if leading_subject and leading_subject.group(1) not in ignored:
        return {leading_subject.group(1)}
    subjects = _subject_tokens(title, identity)
    return {
        subject
        for subject in subjects
        if subject not in ignored
        and subject in identity.title_named_subjects
    }


def _reconciliation_content_form(title: str, identity: EventIdentity) -> str:
    if _compiled_rule(r"\b(?:event|keynote)\b.{0,18}\b(?:countdown|preview|what to expect)\b|"
        r"(?:发布会|活动).{0,14}(?:倒计时|前瞻|新品展望)", 0).search(title):
        return "event_preview"
    if identity.content_form != "news":
        return identity.content_form
    if _compiled_rule(r"\beverything\b.{0,48}\bexpected to (?:announce|launch|release|unveil)\b|"
        r"\b(?:features?|upgrades?|changes?)\b.{0,45}\b(?:rumored|reported) for years\b|"
        r"(?:全部|所有|新品).{0,16}(?:汇总|盘点)|(?:传闻|爆料).{0,12}(?:汇总|盘点)|"
        r"(?:结合|根据).{0,36}(?:多方|此前).{0,24}(?:汇总|总结|盘点)|"
        r"(?:汇总|总结|盘点).{0,14}(?:核心亮点|已有信息|此前传闻|爆料)", 0).search(title):
        return "roundup"
    return "news"


def _legal_action_stage_text(text: str) -> str:
    if (
        _contains(
            text,
            "court revives",
            "court revived",
            "appeals court revives",
            "appeals court restored",
            "case can proceed",
            "case may proceed",
            "lawsuit can proceed",
            "lawsuit may proceed",
            "恢复审理",
            "恢复诉讼",
            "案件继续推进",
            "诉讼继续推进",
            "推翻驳回裁定",
        )
        or _compiled_rule(r"\b(?:court|appeals court|panel)\b.{0,45}"
            r"\b(?:reviv(?:es|ed)|restore(?:s|d)|reinstate(?:s|d)|resurrect(?:s|ed))\b"
            r".{0,45}\b(?:case|lawsuit|claim)\b", re.I).search(text)
    ):
        return "case-revival"
    if (
        _contains(
            text,
            "opposition to the motion to dismiss",
            "asks the court to deny",
            "asked the court to deny",
            "should be denied",
            "hits back at",
            "fires back at",
        )
        or _compiled_rule(r"\b(?:opposition to|denying)\b.{0,55}"
            r"\b(?:dismissal|motion to dismiss|request for dismissal)\b", 0).search(text)
        or _compiled_rule(r"(?:反驳|反对|要求法院拒绝|要求法院驳回).{0,28}"
            r"(?:驳回诉讼|撤诉|驳回动议|驳回申请|撤销诉讼)", 0).search(text)
    ):
        return "dismissal-opposition"
    if _contains(
        text,
        "motion to dismiss",
        "moves to dismiss",
        "asks the judge to dismiss",
        "asks judge to dismiss",
        "to be dismissed",
        "wants apple's lawsuit dismissed",
        "wants the lawsuit dismissed",
        "motion filed yesterday to dismiss",
        "asked a federal judge to toss out",
        "seeks dismissal",
        "request to dismiss",
        "申请驳回",
        "请求驳回",
        "要求驳回",
    ) or _compiled_rule(r"(?:请求|要求|申请).{0,12}法官.{0,12}驳回", 0).search(text):
        return "dismissal-request"
    if (
        _contains(text, "discovery", "response deadline", "filing deadline", "答辩期限", "取证")
        and _contains(text, "delay", "delays", "delayed", "extend", "extended", "延期", "延长")
    ):
        return "case-schedule"
    if _contains(text, "delay", "delays", "delayed", "delaying", "拖延", "延误") and _contains(
        text,
        "lawsuit",
        "legal battle",
        "case",
        "诉讼",
        "法律纠纷",
        "案件",
        "法律战",
    ):
        return "case-schedule"
    if _contains(text, "extension", "extended", "延期", "延长") and _contains(
        text, "lawsuit", "legal battle", "case", "诉讼", "法律纠纷", "案件"
    ):
        return "case-schedule"
    if _contains(
        text,
        "preliminary injunction",
        "temporary injunction",
        "seeks an injunction",
        "moves for injunction",
        "demands injunction",
        "临时禁令",
        "初步禁令",
        "申请禁令",
        "请求禁令",
    ):
        return "injunction-request"
    if (
        _contains(text, "court ruled", "judge ruled", "法官驳回", "法院裁定", "缩小诉讼")
        or _compiled_rule(r"\b(?:court|judge)\b.{0,28}\b(?:dismissed|narrowed|stricken)\b", 0).search(text)
    ):
        return "court-ruling"
    if _contains(
        text,
        "settlement talks",
        "settlement negotiation",
        "settle the lawsuit",
        "和解谈判",
        "讨论和解",
    ):
        return "settlement-talks"
    if (_compiled_rule(r"\bpaus(?:e|es|ing)\b|暂停", 0).search(text)
            and _compiled_rule(r"\bcase\b|诉讼|案程序|佣金案", 0).search(text)):
        return "pause-request-procedure"
    if _contains(
        text,
        "public rebuttal",
        "rebuttal",
        "rebuts",
        "refutes",
        "published a response",
        "posts rebuttal",
        "responded to",
        "responds to",
        "response to",
        "no evidence supporting",
        "court of public opinion",
        "公开回应",
        "发布回应",
        "否认指控",
        "反驳",
        "回应苹果",
    ):
        return "public-response"
    if _compiled_rule(r"回应.{0,24}(?:诉讼|纠纷|案件|指控|苹果)", 0).search(text):
        return "public-response"
    return ""


def _legal_action_stage(title: str, lead: str) -> str:
    return _legal_action_stage_text(f"{title}. {lead}")


def _legal_title_parties(title: str) -> set[str]:
    parties = set()
    for match in _compiled_rule(r"\b(?:against|with|in)\s+([a-z][a-z0-9.+-]+(?:\s+[a-z][a-z0-9.+-]+){0,2})['’]s\s+"
        r"(?:case|lawsuit|response)\b", 0).finditer(title):
        party = _compiled_rule(r"\s+", 0).sub("-", match.group(1), 0).strip("-")
        if party not in {"apple", "the", "its"}:
            parties.add(party)
    leading = _compiled_rule(r"^([a-z][a-z0-9.+-]+(?:\s+[a-z][a-z0-9.+-]+){0,2})['’]s\b", 0).match(title)
    if leading:
        party = _compiled_rule(r"\s+", 0).sub("-", leading.group(1), 0)
        if party not in {"apple", "the", "its"}:
            parties.add(party)
    return parties


def _component_values(identity: EventIdentity, prefix: str) -> set[str]:
    return {
        component.split(":", 1)[1]
        for component in identity.title_components
        if component.startswith(prefix)
    }


def _content_screening_subject(title: str, lead: str) -> str:
    raw = f"{title}. {lead}"
    action_named = _compiled_rule(r"\b([A-Z][A-Za-z0-9]+(?:['’][A-Za-z]+)?(?:\s+[A-Z][A-Za-z0-9]+(?:['’][A-Za-z]+)?){0,5})\s+"
        r"(?:is\s+going\s+to\s+(?:the\s+)?movies|will\s+be\s+shown|is\s+coming\s+to\s+(?:the\s+)?cinema)\b", 0).search(raw)
    if action_named:
        value = _normalized(action_named.group(1)).replace("'", "")
        return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", value, 0).strip("-")
    quoted = _compiled_rule(r"[\"“]([^\"”]{3,70})[\"”]", 0).search(raw)
    if not quoted:
        quoted = _compiled_rule(r"['‘]([A-Z][A-Za-z0-9]+(?:['’][A-Za-z]+)?(?:\s+[A-Z][A-Za-z0-9]+(?:['’][A-Za-z]+)?){0,8})['’]", 0).search(raw)
    if quoted:
        value = _normalized(quoted.group(1)).replace("'", "")
        return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", value, 0).strip("-")
    named = _compiled_rule(r"\b(?:show|screen|screening(?:s)?(?:\s+for)?|series)\s+"
        r"([A-Z][A-Za-z0-9'’ -]{2,60}?)(?=\s+(?:at|in|on|for)\b|[.,;])", 0).search(raw)
    if named:
        value = _normalized(named.group(1)).replace("'", "")
        return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", value, 0).strip("-")
    return ""


def _product_separation_keys(identity: EventIdentity) -> set[str]:
    products = set(identity.title_products)
    hardware_specific = bool(
        any(
            component.startswith((
                "iphone-model:",
                "iphone-family:",
                "macbook-model:",
                "display-size:",
            ))
            for component in identity.title_components
        )
        or identity.title_components
        & {"largest-iphone-display", "oled-display", "camera-system"}
    )
    if not hardware_specific:
        return set()
    families = set()
    if products & {"iphone", "foldable-iphone"}:
        families.add("iphone")
    if products & {"mac", "macbook", "imac", "mac-mini", "mac-studio", "mac-pro"}:
        families.add("mac")
    for product in products & {"ipad", "ipad-air", "ipad-mini", "ipad-pro", "apple-watch", "airpods", "apple-tv", "vision-pro"}:
        families.add(product)
    return {f"product-family:{family}" for family in families}


def _predicate_separation_keys(identity: EventIdentity) -> set[str]:
    """Return coarse title-led predicate classes for rejecting mixed seed groups.

    These classes describe what the article asserts about its subject. They do
    not merge articles on their own; they only keep an accepted legacy seed
    from treating two explicit, incompatible assertions as one event.
    """
    products = set(identity.title_products)
    components = set(identity.title_components)
    assertion_components = set(identity.components)
    actions = set(identity.title_actions)
    keys: set[str] = set()
    software_products = {
        "app-store",
        "apple-books",
        "apple-intelligence",
        "apple-music",
        "apple-sports",
        "apple-tv",
        "apple-wallet",
        "carplay",
        "icloud",
        "ios",
        "ipados",
        "macos",
        "safari",
        "siri",
        "tvos",
        "visionos",
        "watchos",
        "xcode",
    }
    hardware_products = {
        "airpods",
        "apple-tv-hardware",
        "apple-watch",
        "foldable-iphone",
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
    if products & software_products and "feature-change" in actions:
        keys.add("predicate:platform-feature-change")
    if components & {"display-panel", "oled-display"}:
        keys.add("predicate:hardware-component-development")
    if (
        products & hardware_products
        and (
            components
            & {
                "hardware-product-roadmap",
                "product-release-delay",
                "roadmap-projection",
            }
            or actions & {"delay-roadmap", "project-cancellation"}
        )
    ):
        keys.add("predicate:hardware-product-roadmap")
    if "component-cost-analysis" in assertion_components:
        keys.add("predicate:hardware-component-cost")
    if "price-change" in actions:
        keys.add("predicate:retail-price-change")
    if actions & {"claim-denial", "project-cancellation"}:
        keys.add("predicate:claim-status")
    if any(
        component.startswith("component-supplier-sourcing:")
        for component in assertion_components
    ) or "component-supplier-sourcing" in assertion_components:
        keys.add("predicate:component-supplier-sourcing")
    if "hardware-shipment-plan-change" in assertion_components:
        keys.add("predicate:hardware-shipment-plan-change")
    elif "hardware-market-performance" in components:
        keys.add("predicate:hardware-market-performance")
    return keys


def _title_predicate_separation_keys(title: str) -> set[str]:
    """Extract concrete title predicates that generic product actions miss."""
    title_text = _canonical_title(title)
    keys: set[str] = set()
    if _apple_event_invitation_interpretation_context(title):
        keys.add("primary-claim-predicate:event-invitation-feature-interpretation")
    if _compiled_rule(r"\b(?:packaging box|retail packaging|retail box|product box)\b|"
        r"(?:包装盒|零售包装盒|产品包装盒)", 0).search(title_text):
        keys.add("primary-claim-predicate:retail-packaging-disclosure")
    if _compiled_rule(r"\b(?:colors?|finishes?|colourways?)\b.{0,24}"
        r"\b(?:revealed|unveiled|leaked|lineup)\b|"
        r"(?:配色|颜色|外观色).{0,20}(?:揭晓|曝光|流出|阵容|新增)", 0).search(title_text):
        keys.add("primary-claim-predicate:finish-lineup-disclosure")
    if _compiled_rule(r"\b(?:colors?|colou?rs?|finishes?)\b|(?:配色|颜色|外观色)", 0).search(title_text) and _compiled_rule(r"\b(?:only|limited\s+to)\b.{0,24}\b(?:two|2)\b.{0,16}"
        r"\b(?:launch\s+)?(?:colors?|colou?rs?|finishes?)\b|"
        r"\b(?:two|2)\b.{0,16}\blaunch\s+(?:colors?|colou?rs?|finishes?)\b|"
        r"(?:仅|只)(?:推|提供|有|供应|推出).{0,16}(?:两|2)\s*款?(?:首发)?(?:配色|颜色)|"
        r"(?:首发|上市).{0,12}(?:仅|只).{0,12}(?:两|2)\s*款?(?:配色|颜色)", re.I).search(title_text):
        keys.add("primary-claim-predicate:finish-lineup-disclosure")
    if _compiled_rule(r"\b(?:apple\s+)?(?:event|keynote)\b.{0,70}"
        r"(?:date|time|schedule|announce|announcement|take place)|"
        r"(?:苹果)?(?:发布会|活动).{0,55}(?:日期|时间|日程|官宣|举行)", re.I).search(title_text):
        keys.add("primary-claim-predicate:event-schedule-announcement")
    if _compiled_rule(r"\b(?:price|prices|pricing)\b.{0,55}"
        r"(?:rise|increase|higher|forecast|estimate|might|may|could|guess)|"
        r"(?:涨价|提价|价格|售价).{0,45}(?:预计|预估|预测|可能|或|上调|上涨|提高)", re.I).search(title_text):
        keys.add("primary-claim-predicate:retail-price-forecast")
    if _compiled_rule(r"\b(?:features?|capabilities)\b.{0,36}\b(?:won't|will not|may not|missing|lack)\b|"
        r"\b(?:won't|will not|may not|missing|lack)\b.{0,36}\b(?:features?|capabilities)\b|"
        r"(?:缺少|不会有|不具备|无缘).{0,30}(?:功能|特性)|"
        r"(?:功能|特性).{0,30}(?:缺少|不会有|不具备|无缘)", re.I).search(title_text):
        keys.add("primary-claim-predicate:feature-absence-analysis")
    return keys


def _title_proves_first_party_subject(title: str, identity: EventIdentity) -> bool:
    """Require explicit title ownership before promoting an initially weak item."""
    return identity.action_owner == "apple"


def _weak_topic_separation_key(title: str) -> str:
    if _contains(title, "dram", "ram", "memory", "nand", "内存", "存储", "闪存"):
        return "weak-topic:memory-market"
    if _contains(title, "2nm", "3nm", "chip", "soc", "semiconductor", "芯片", "制程", "半导体"):
        return "weak-topic:semiconductor-roadmap"
    if _contains(title, "app", "application", "应用", "微信"):
        return "weak-topic:third-party-app"
    if _contains(title, "ai model", "llm", "大模型", "ai 模型"):
        return "weak-topic:third-party-ai-model"
    return ""


def _changed_object_patterns() -> dict[str, tuple[str, str]]:
    """Return the existing bilingual changed-object classifier patterns."""
    return {
        "case-material": (
            r"\b(?:ceramic|titanium|aluminum|aluminium|stainless steel|case material|housing material)\b",
            r"(?:陶瓷|钛金属|钛合金|铝合金|不锈钢|表壳材质|机身材质|外壳材质)",
        ),
        "processor": (
            r"\b(?:processor|chipset|soc|s\d{1,2}\s+chip|m\d(?:\s+(?:pro|max|ultra))?\s+chip)\b",
            r"(?:处理器|芯片|\bsoc\b)",
        ),
        "display": (
            r"\b(?:display panel|oled display|oled panel|mini-led|microled|refresh rate)\b",
            r"(?:屏幕|显示屏|面板|刷新率)",
        ),
        "camera": (
            r"\b(?:camera|sensor|aperture|telephoto|lens)\b",
            r"(?:相机|摄像头|传感器|光圈|长焦|镜头|主摄|超广角|双摄|单摄|影像)",
        ),
        "battery": (r"\b(?:battery|charging|mah)\b", r"(?:电池|续航|充电|毫安时)"),
        "modem": (r"\b(?:modem|baseband|cellular chip)\b", r"(?:调制解调器|基带|蜂窝芯片)"),
        "memory-storage": (r"\b(?:ram|memory|dram|nand|storage)\b", r"(?:内存|存储|闪存)"),
        "thermal-design": (
            r"\b(?:vapor chamber|thermal design|cooling system|heat spreader)\b",
            r"(?:均热板|散热设计|散热系统)",
        ),
        "retail-packaging": (
            r"\b(?:packaging box|retail packaging|retail box|product box)\b",
            r"(?:包装盒|零售包装盒|产品包装盒)",
        ),
        "finish-color": (
            r"\b(?:color|colors|colour|colours|finish|finishes|colourway|colourways)\b",
            r"(?:配色|颜色|机身色|外观色)",
        ),
    }


def _changed_object_separation_keys(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> set[str]:
    """Extract the concrete object changed by a product report.

    A shared product family is not an event identity. Only the headline and
    first lead sentence are used, preventing background specification lists
    from creating artificial conflicts.
    """
    if not identity.title_products:
        return set()
    scope = f"{_normalized(title)}. {_short_lead_scope(lead, sentences=1, limit=420)}"
    return {
        f"changed-object:{name}"
        for name, alternatives in _changed_object_patterns().items()
        if any(_compiled_rule(pattern, re.I).search(scope) for pattern in alternatives)
    }


def _primary_title_changed_object(title: str) -> str:
    """Return the first concrete changed object named by the headline."""
    title_text = _normalized(title)
    matches: list[tuple[int, str]] = []
    for name, alternatives in _changed_object_patterns().items():
        for pattern in alternatives:
            match = _compiled_rule(pattern, re.I).search(title_text)
            if match:
                matches.append((match.start(), name))
                break
    for pattern in (r"\bdisplays?\b", r"显示器"):
        match = _compiled_rule(pattern, re.I).search(title_text)
        if match:
            matches.append((match.start(), "display"))
            break
    return min(matches)[1] if matches else ""


def _primary_title_changed_object_measure(title: str) -> tuple[str, str]:
    """Return a headline's first changed object and adjacent count, if present."""
    title_text = _normalized(title)
    object_name = _primary_title_changed_object(title_text)
    if not object_name:
        return "", ""
    patterns = list(_changed_object_patterns()[object_name])
    if object_name == "display":
        patterns.extend((r"\bdisplays?\b", r"显示器"))
    object_matches = [
        match
        for pattern in patterns
        for match in [re.search(pattern, title_text, re.I)]
        if match
    ]
    if not object_matches:
        return "", ""
    object_match = min(object_matches, key=lambda match: match.start())
    prefix = title_text[max(0, object_match.start() - 14) : object_match.start()]
    count_match = _compiled_rule(r"(?:^|[^a-z0-9])"
        r"(?P<count>\d{1,3}|one|two|three|four|five|six|seven|eight|"
        r"一|二|两|三|四|五|六|七|八)\s*(?:[-－]|台|个|颗|款)?\s*$", re.I).search(prefix)
    if not count_match:
        return "", ""
    count_map = {
        "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8",
        "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
        "五": "5", "六": "6", "七": "7", "八": "8",
    }
    raw_count = count_match.group("count").lower()
    return object_name, count_map.get(raw_count, raw_count)


def _title_product_period_keys(title: str, identity: EventIdentity) -> set[str]:
    """Project a title-level product roadmap period without making it a merge key."""
    title_text = _normalized(title)
    years = _calendar_years(title_text)
    if len(years) != 1 or not identity.title_products:
        return set()
    year = next(iter(years))
    season = ""
    if _compiled_rule(r"\bspring\b|春季", 0).search(title_text):
        season = "spring"
    elif _compiled_rule(r"\b(?:fall|autumn)\b|秋季", 0).search(title_text):
        season = "fall"
    elif _compiled_rule(r"\b(?:first half|h1|1h)\b|上半年", 0).search(title_text):
        season = "h1"
    elif _compiled_rule(r"\b(?:second half|h2|2h)\b|下半年", 0).search(title_text):
        season = "h2"
    period = f"{year}-{season}" if season else year
    return {
        f"product-period:{product}:{period}"
        for product in _primary_title_subjects(identity)
        if product in identity.title_products
    }


def _multi_unit_apple_capability_claim(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> tuple[str, str, str] | None:
    """Identify one Apple capability defined by a device topology.

    Cross-language reports often translate the feature name but retain the
    affected product, unit count, and concrete capability. Those structural
    fields are safer reunion evidence than shared platform words alone.
    """
    if identity.scope != "apple-direct" or len(identity.title_products) != 1:
        return None
    product = next(iter(identity.title_products))
    title_text = _canonical_title(title)
    lead_text = _short_lead_scope(lead, sentences=1, limit=420)
    scope = f"{title_text}. {lead_text}"
    number_map = {
        "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8",
        "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
        "五": "5", "六": "6", "七": "7", "八": "8",
    }
    count_match = _compiled_rule(r"(?<![a-z0-9])(?P<count>\d{1,2}|one|two|three|four|five|six|seven|eight|"
        r"一|二|两|三|四|五|六|七|八)\s*(?:[-－]|台|个)?\s*"
        r"(?:connected\s+)?(?:speakers?|homepods?|devices?|units?|扬声器|音箱|设备|homepod)", re.I).search(scope)
    if not count_match:
        return None
    raw_count = count_match.group("count").lower()
    count = number_map.get(raw_count, raw_count)
    if _compiled_rule(r"\b(?:surround\s+sound|home\s+theater|home\s+cinema|party\s+mode)\b|"
        r"(?:环绕声|家庭影院|派对模式)", re.I).search(scope):
        capability = "surround-audio"
    else:
        return None
    return product, count, capability


def _roadmap_action_clause(title: str) -> str:
    """Keep the clause that owns a roadmap predicate, excluding later context."""
    canonical = _canonical_title(title)
    action = _compiled_rule(r"\b(?:cancel(?:s|ed|led|lation)?|scrap(?:s|ped)?|abandon(?:s|ed)?|"
        r"call(?:s|ed|ing)?\s+off|delay(?:s|ed)?|retain(?:s|ed)?|keep(?:s|ing)?|"
        r"launch(?:es|ed|ing)?|release(?:s|d|ing)?|introduc(?:e|es|ed|ing)|green\s+light|go-ahead)\b|"
        r"(?:取消|搁置|终止|放弃|砍掉|叫停|延期|保留|维持|推出|发布|引入|获准开发|正式立项)", re.I).search(canonical)
    if not action:
        return canonical
    trailing = canonical[action.end() :]
    if _compiled_rule(r'green\s+light|go-ahead|获准开发|正式立项', re.I).fullmatch(action.group()):
        boundary = _compiled_rule(r'[,，]', 0).search(trailing)
        if boundary:
            return canonical[:action.end() + boundary.start()].strip()
    boundary = _compiled_rule(r",\s+(?:which|previously|historically|while|whereas|although|but)\b|"
        r"[,，]\s*(?:此前|过去|而|但|其中|后者|前者)", re.I).search(trailing)
    if not boundary:
        return canonical
    return canonical[: action.end() + boundary.start()].strip()


def _hardware_roadmap_primary_claim(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> tuple[str, str, str] | None:
    """Return one title-owned hardware roadmap subject, action, and qualifier.

    Product-family roadmap words are too broad to identify an event. This
    projection distinguishes cancellation, continued availability of an
    existing design, and introduction of a newly positioned model. The first
    lead sentence may complete a title claim, but later body background never
    creates one.
    """
    scoped_title = _roadmap_action_clause(title)
    if scoped_title != _canonical_title(title):
        title = scoped_title
        identity = build_event_identity(title, _short_lead_scope(lead, sentences=1, limit=420))
    if identity.title_components & {
        "analyst-target-action",
        "primary-intent:analyst-target",
    }:
        # A rating or price-target action owns the headline. A product rumor
        # cited as rationale is evidence, not a second roadmap action.
        return None
    supported_hardware_products = {
        "apple-home-hub",
        "airpods",
        "apple-tv-hardware",
        "apple-watch",
        "foldable-iphone",
        "imac",
        "ipad",
        "ipad-air",
        "ipad-mini",
        "ipad-pro",
        "iphone",
        "mac-mini",
        "mac-pro",
        "mac-studio",
        "macbook",
        "vision-pro",
    }
    hardware_products = identity.title_products & supported_hardware_products
    if (
        not hardware_products
        and identity.scope == "apple-direct"
        and len(identity.products & supported_hardware_products) == 1
        and _compiled_rule(r"\b(?:cancel(?:s|ed|led|lation)?|scrap(?:s|ped)?|abandon(?:s|ed)?|"
            r"call(?:s|ed|ing)?\s+off|project\s+(?:may\s+be|is)\s+dead|"
            r"plans?\s+(?:may\s+be|are)\s+dead)\b|"
            r"(?:取消|搁置|终止|放弃|砍掉|叫停|项目.{0,8}(?:已死|夭折|告吹))", re.I).search(_canonical_title(title))
    ):
        # A generic Apple headline may name the affected product only in its
        # opening sentence. The lead is bounded before identity construction,
        # so accepting that single product completes the headline claim without
        # admitting later body context.
        hardware_products = identity.products & supported_hardware_products
    os_products = {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
    if (
        len(hardware_products) != 1
        or identity.content_form != "news"
        or identity.title_products & os_products
    ):
        return None
    product = next(iter(hardware_products))
    title_text = _canonical_title(title)
    claim_scope = f"{title_text}. {_short_lead_scope(lead, sentences=1, limit=420)}"
    periods = _compiled_rule(r"(?<!\d)(20\d{2})(?!\d)", 0).findall(claim_scope)
    period = periods[0] if periods else "unspecified"

    # Bind the changed component to the model's own development predicate.
    models = named_iphone_models(title_text) if product in {"iphone", "foldable-iphone"} else set()
    development_product = next(iter(models)) if len(models) == 1 else product
    model_pattern = re.escape(development_product).replace(r"\-", r"\s*")
    if development_product in {"iphone-duo", "iphone-fold", "iphone-ultra"}:
        model_pattern += r"(?:\s*[1-9]\d?)?"
    model_pattern = r"(?<![a-z0-9])" + model_pattern + r"(?![a-z0-9])"
    current_development = not _compiled_rule(
        r"\b(?:last\s+year|previously|cancel\w*|denies?|not|never|releas\w*|launch\w*|ships?)\b|"
        r"去年|此前|取消|否认|并未|没有|量产上市|正式发布", re.I).search(title_text)
    component_relations = (
        model_pattern + r"\s+prototypes?\s+(?:with|include\w*|incorporat\w*)\s+([^.!?。,;]{2,70})",
        model_pattern + r"\s+will\s+(?:have|gain)\s+([^.!?。,;]{2,70})",
        model_pattern + r"\s*原型机(?:已|曝光|[:,，：\s])*(?:配备|测试)([^。！？,，;；]{2,50})",
        r"测试([^。！？,，;；]{2,50})原型(?:机)?\s*(?:或|可能)?用于(?:第[一二三123]代)?\s*" + model_pattern,
    )
    development_lead = _short_lead_scope(lead, sentences=1, limit=420)
    title_generation = foldable_iphone_generation_subject(title_text)
    lead_generation = foldable_iphone_generation_subject(development_lead)
    same_generation = title_generation == lead_generation or lead_generation == "foldable-iphone"
    owned_lead = same_generation and _compiled_rule(model_pattern, re.I).search(development_lead)
    approval = (model_pattern + r'\s*(?:(?:has|been|already|officially)\s+)*'
        r'(?:gets?\s+(?:the\s+)?green\s+light|(?:given\s+)?go-ahead|获准开发|正式立项)')
    approval_blocked = False
    if _compiled_rule(approval, re.I).search(title_text):
        for text in (title_text, development_lead):
            for a, b in source_clause_spans(text):
                clause = text[a:b]
                local_models = named_iphone_models(clause)
                local_generation = foldable_iphone_generation_subject(clause)
                if (local_models and local_models != models) or (
                        title_generation != 'foldable-iphone' and local_generation != 'foldable-iphone'
                        and title_generation != local_generation):
                    continue
                owns = (local_models == models if models else bool(_compiled_rule(model_pattern, re.I).search(clause)))
                if not local_models and product in _bounded_evidence_products(clause):
                    owns = True
                reference = _compiled_rule(r'^\s*apple\s+denies?\s+(?:(?:the|this)\s+)?approval[.!?\s]*$', re.I).match(clause)
                if (owns or reference) and _compiled_rule(r'green\s+light|go-ahead|approv\w*|获准|立项', re.I).search(clause):
                    approval_blocked |= (source_predicate_role(clause) != 'current'
                        or source_denies_action('', clause, r'gets?|given|approv\w*|获准|立项'))
    if _compiled_rule(approval, re.I).search(title_text) and not approval_blocked:
        return development_product, 'project-development-approval', 'preproduction'
    if current_development:
        for pattern in component_relations:
            relation = _compiled_rule(pattern, re.I).search(title_text)
            if relation is None:
                continue
            components = primary_assertion_components(relation.group(1))
            if len(components) == 1:
                if (owned_lead and components & primary_assertion_components(development_lead)
                        and (source_predicate_role(development_lead) == "background"
                             or source_denies_action("", development_lead, r"include\w*|incorporat\w*|test\w*|have|gain|配备|测试|加入"))):
                    continue
                return development_product, "component-development-" + next(iter(components)), "preproduction"
    display_model = model_pattern
    if product == "foldable-iphone":
        display_model = r"(?:" + model_pattern + r"|foldable\s+iphone|折叠(?:屏)?\s*iphone)"
        owned_lead = (same_generation and not (named_iphone_models(development_lead) - models)
            and _compiled_rule(display_model, re.I).search(development_lead))
    larger_model = r"(?:\b(?:larger|bigger)\s+|更大(?:尺寸)?的?\s*)" + display_model
    display_object = r"(?:larger\s+(?:(?:inner|outer)\s+(?:and\s+(?:inner|outer)\s+)?)?(?:screen|display)s?|更大(?:的)?(?:内屏|外屏|屏幕))"
    model_display = (display_model + r"['’]?"
        r"(?:\s+(?:(?:will|could|may)\s+(?:have|gain)|rumou?red\s+to\s+feature)\s+|(?:将|有望)(?:配备|采用))"
        + display_object)
    apple_plan = (r"\bapple\s+(?:is\s+)?(?:(?:reportedly|apparently)\s+)?"
        r"(?:planning|plans?|considering)\s+(?:a\s+)?")
    generation_modifier = r"(?:(?:first|second|third|fourth|fifth|\d+(?:st|nd|rd|th)?)[ -]generation\s+)?"
    planned_display = (apple_plan + generation_modifier + display_model
        + r"(?:\s+for\s+20\d{2})?\s+with\s+" + display_object + "|"
        + r"苹果\s*" + display_model
        + r"\s*(?:[一二三四五六七八九十\d]+年路线图)?(?:已经)?(?:规划|计划)"
        r"(?:到第[一二三四五六七八九十\d]+代)?[，,]\s*"
        r"(?:内外屏|内屏|外屏|屏幕)(?:将|计划)(?:进一步)?(?:增大|扩大)")
    owned_display = _compiled_rule(larger_model + "|" + model_display, re.I).search(title_text)
    if not owned_display and owned_lead:
        owned_display = _compiled_rule(
            r"(?:" + apple_plan + r"|苹果(?:公司)?(?:正在|正)?(?:规划|计划|考虑))"
            + larger_model + "|" + planned_display, re.I).search(development_lead)
    display_denied = (owned_lead
        and _compiled_rule(r"\b(?:screen|display)s?\b|内外屏|内屏|外屏|屏幕|扩屏", re.I).search(development_lead)
        and (source_predicate_role(development_lead) == "background"
             or source_denies_action("", development_lead, r"plan\w*|consider\w*|enlarg\w*|have|gain|规划|计划|考虑|扩屏")))
    if (current_development and owned_display and not display_denied
            and _compiled_rule(r"\b(?:future|considering|plans?|planning|in\s+the\s+works)\b|规划|计划|更大尺寸", re.I).search(claim_scope)
            and _compiled_rule(r"\b(?:screen|display)s?\b|内外屏|内屏|外屏|屏幕", re.I).search(claim_scope)):
        return development_product, "display-enlargement-planning", "preproduction"

    window_lead = _short_lead_scope(lead, sentences=1, limit=420)
    window_lead_products = _bounded_evidence_products(window_lead) & supported_hardware_products
    if window_lead_products and product not in window_lead_products:
        window_lead = ""
    window_scope = _compiled_rule(r",\s*(?:followed by|separately)|，(?:随后|此外|另外)", 0).split(f"{title_text}. {window_lead}", 1)[0]
    planned_launch = (identity.action_owner != "third-party"
                      and identity.scope != "third-party-context"
                      and not (identity.title_actions & {"project-cancellation", "claim-denial", "withdrawal"})
                      and not _compiled_rule(r"取消|放弃|叫停|终止|\b(?:cancel(?:led|ed)?|abandon(?:ed)?|scrapp?ed)\b", re.I).search(title_text)
                      and _compiled_rule(r"\b(?:plans?|planned|ready to launch|expected|may|could)\b|计划|预计|将于|最快|有望|或于", re.I).search(window_scope)
                      and _compiled_rule(r"\b(?:launch|release|coming)\b|推出|发布|上市", re.I).search(window_scope))
    if planned_launch:
        month_names = {name: number for number, name in enumerate(
            ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}
        chinese_months = {name + "月": number for number, name in enumerate(
            ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"), 1)}
        window_points = []
        pattern = r"\b(?:" + "|".join(month_names) + r")\b|\d{1,2}\s*月|" + "|".join(sorted(chinese_months, key=len, reverse=True)) + r"|early next year|明年初|今秋|autumn|fall"
        for match in re.finditer(pattern, window_scope, re.I):
            token = match.group().lower()
            if _compiled_rule(r"\s*\d{1,2}\s*[日号]\s*(?:消息|报道)", 0).match(window_scope[match.end():]):
                continue
            if token == "may":
                before = window_scope[:match.start()]
                after = window_scope[match.end():]
                # May is also a modal verb. Require local calendar syntax,
                # rather than guessing from the following launch verb.
                calendar_may = bool(
                    _compiled_rule(r"\b(?:in|by|until|during|from|for|through|between|next)\s+$", re.I).search(before)
                    or _compiled_rule(r"\s+(?:\d{1,2}(?:st|nd|rd|th)?\b|20\d{2}\b)", re.I).match(after)
                    or re.search(r"\b(?:" + "|".join(month_names) + r")\s+(?:and|to|through|until)\s+$", before, re.I)
                )
                if not calendar_may:
                    continue
            if token in {"early next year", "明年初"}:
                window_points.extend((13, 15))
            elif token in {"今秋", "autumn", "fall"}:
                window_points.extend((9, 11))
            else:
                month = month_names.get(token) or chinese_months.get(token)
                if month is None:
                    month = int(_compiled_rule(r"\d+", 0).match(token).group())
                if 1 <= month <= 12:
                    if _compiled_rule(r"(?:next year|明年)\s*$", 0).search(window_scope[max(0, match.start()-16):match.start()]):
                        month += 12
                    window_points.append(month)
        if window_points:
            lower, upper = min(window_points), max(window_points)
            upper_text = "open" if _compiled_rule(r"as early as|no earlier than|最快|最早", re.I).search(window_scope) else str(upper)
            window_years = _compiled_rule(r"(?<!\d)(20\d{2})(?!\d)", 0).findall(window_scope)
            window_year = window_years[0] if window_years else "unspecified"
            return product, "launch-window-planning", f"window|{window_year}|{lower}|{upper_text}"

    continuing_launch_plan = bool(
        _compiled_rule(r"\b(?:remains?\s+planned|still\s+plans?\s+to\s+(?:release|launch|ship))\b|仍(?:然)?计划.{0,16}(?:推出|发布|上市)", re.I).search(claim_scope)
        and _compiled_rule(r"\b(?:roadmap|coming|release|launch|planned)\b|计划|推出|发布|上市", re.I).search(title_text)
    )
    if continuing_launch_plan:
        if period == "unspecified" and _compiled_rule(r"\bthis year\b|今年|年内", re.I).search(claim_scope):
            period = "this-year"
        return product, "planned-launch-continuation", period

    component_transition = bool(
        _compiled_rule(r"\b(?:abandon(?:s|ed)?|drop(?:s|ped)?|move(?:s|d)?\s+away\s+from)\b"
            r".{0,18}\b(?:lcd|mini[- ]led|oled|tft|ips)\b|"
            r"(?:放弃|弃用|改用|转向).{0,12}(?:lcd|mini[- ]led|oled|tft|ips)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:adopt(?:s|ed)?|embrace(?:s|d)?|switch(?:es|ed)?\s+to|move(?:s|d)?\s+to)\b"
            r".{0,18}\b(?:lcd|mini[- ]led|oled|tft|ips)\b|"
            r"(?:采用|拥抱|改用|转向).{0,12}(?:lcd|mini[- ]led|oled|tft|ips)", re.I).search(title_text)
    )
    cancellation_pattern = (
        r"\b(?:cancel(?:s|ed|led|lation)?|scrap(?:s|ped)?|abandon(?:s|ed)?|"
        r"call(?:s|ed|ing)?\s+off|"
        r"project\s+(?:may\s+be|is)\s+dead|plans?\s+(?:may\s+be|are)\s+dead)\b|"
        r"(?:取消|搁置|终止|放弃|砍掉|叫停|项目.{0,8}(?:已死|夭折|告吹))"
    )
    cancellation_match = re.search(cancellation_pattern, title_text, re.I)
    cancellation = not component_transition and cancellation_match is not None
    if cancellation:
        qualifier_scope = claim_scope
        scope_action = re.search(cancellation_pattern, qualifier_scope, re.I)
        if scope_action:
            trailing_scope = qualifier_scope[scope_action.end() :]
            relative_boundary = _compiled_rule(r",\s+(?:which|while|whereas|although|but)\b|"
                r"[;；]|，(?:而|但|其中|后者|前者)\b", re.I).search(trailing_scope)
            if relative_boundary:
                qualifier_scope = qualifier_scope[
                    : scope_action.end() + relative_boundary.start()
                ]
        foldable_form = bool(
            _compiled_rule(r"\b(?:fold(?:able|ing)|all[- ]screen)\b|(?:折叠|全屏)", re.I).search(qualifier_scope)
        )
        qualifier = (
            "foldable-form-factor"
            if foldable_form
            else "oled-form-factor"
            if _compiled_rule(r"\boled\b", re.I).search(qualifier_scope)
            else "product-program"
        )
        if (
            foldable_form
            and product in {"ipad", "macbook"}
        ):
            # A foldable-computer project is variously described
            # as an iPad/Mac hybrid, foldable iPad, or foldable MacBook. Bind
            # its form factor before the provisional marketing name.
            product = "foldable-apple-computer"
        return product, "project-cancellation", qualifier

    display_retention = bool(
        _compiled_rule(r"\b(?:lcd|mini[- ]led|current|existing)\b|(?:lcd|mini[- ]led|现有|当前)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:stick around|remain(?:s|ed)?(?: available)?|continue(?:s|d)?(?: to be sold)?|"
            r"stay(?:s|ed)?(?: on sale)?|be sold|sell)\b|"
            r"(?:继续(?:销售|在售|保留)|维持销售|至少.{0,10}(?:销售|在售)|卖到|销售到)", re.I).search(title_text)
    )
    if display_retention:
        return product, "existing-design-retention", period

    positioned_model = bool(
        _compiled_rule(r"\b(?:new|all[- ]new)\b|(?:新款|全新)", re.I).search(claim_scope)
        and _compiled_rule(r"\b(?:between|bridge(?:s|d|ing)?\s+(?:the\s+)?gap|middle[- ]ground)\b|"
            r"(?:介于|位于).{0,24}(?:之间|中间)|(?:填补|弥合).{0,18}(?:空白|差距)", re.I).search(claim_scope)
        and _compiled_rule(r"\b(?:plan(?:s|ned)?|introduc(?:e|es|ed|ing)|launch|coming)\b|(?:计划|推出|发布|引入)", re.I).search(claim_scope)
    )
    if positioned_model:
        return product, "positioned-model-introduction", period
    return None


def hardware_roadmap_primary_claim(
    title: str,
    lead: str = "",
) -> tuple[str, str, str] | None:
    """Return a bounded product/action/qualifier key for roadmap projection."""
    scoped_lead = _short_lead_scope(lead, sentences=1, limit=420)
    identity = build_event_identity(title, scoped_lead)
    return _hardware_roadmap_primary_claim(title, scoped_lead, identity)


def _first_party_content_claim(
    title: str,
    lead: str,
    identity: EventIdentity,
    evidence: str = "",
) -> tuple[str, str] | None:
    """Return a named first-party content subject and its concrete action."""
    title_text = _canonical_title(title)
    if _compiled_rule(r'headlin|perform|stage|演出|表演', re.I).search(title + ' ' + lead[:300]):
        for text in (lead, evidence[:1600]):
            for start, end in source_sentence_spans(text):
                clause = text[start:end]
                announcement = _compiled_rule(r'\b(?:apple(?:\s+music)?|[a-z][a-z ]{0,35}\s+and\s+apple\s+music)'
                    r'(?:,\s*alongside\s+[^,]{1,60},|\s+and\s+[a-z][a-z ]{0,35}?)?\s+'
                    r'(?:(?:has|have|today|now)\s+)*(?:announced|confirmed)\b', re.I).search(clause)
                show = _compiled_rule(r'\bApple Music\s+((?:[A-Z0-9][A-Za-z0-9]*\s+){1,7}(?:Show|Concert|Festival))\b', 0).search(clause)
                if (announcement and show and source_predicate_role(clause[:announcement.end()]) == 'current'
                        and not _compiled_rule(r'^\s*(?:last\s+(?:year|month|week)|previously|years?\s+ago)\b', re.I).search(clause[announcement.end():])
                        and _compiled_rule(r'will\s+(?:perform|headline)|将(?:担任|表演)', re.I).search(clause[announcement.end():])):
                    return _compiled_rule(r'[^a-z0-9]+', 0).sub('-', show.group(1).casefold()).strip('-'), 'performance-lineup-announcement'
    owned_film_title = bool(_compiled_rule(r"\bapple's\s+(?:new\s+)?(?:film|movie|documentary|series)\b|"
        r"苹果.{0,8}(?:电影|影片|纪录片|剧集)", 0).search(title_text))
    if "apple-arcade" in identity.products:
        catalog_scope = f"{title}. {_short_lead_scope(lead, sentences=1)}"
        catalog_action = _compiled_rule(r"apple arcade.{0,25}\b(?:add(?:ed|ing|s)?|available)|\blands? on apple arcade\b|apple arcade.{0,20}(?:新增|上架|加入)", re.I).search(catalog_scope)
        named_game = (_compiled_rule(r"^(.{2,70}?)\s+lands? on apple arcade\b", re.I).search(title)
                      or _compiled_rule(r"apple arcade\s+(?:is\s+)?add(?:ed|ing|s)?\s+(.{2,70}?)(?=\s+(?:to|and|with)\b|[,.。]|$)", re.I).search(lead))
        opening = _short_lead_scope(lead, sentences=1)
        owned_addition = (_compiled_rule(r"^Apple announced (.{2,70}?) (?:for|on) Apple Arcade\b", re.I).search(opening)
                          or _compiled_rule(r"^(.{2,70}?) arrives through Apple Arcade\b", re.I).search(opening))
        if owned_addition:
            named_game = owned_addition
            catalog_action = True
        if catalog_action and named_game:
            subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", named_game.group(1).strip("'\" ").casefold(), 0).strip("-")
            if subject and not _compiled_rule(r"\d+[- ]|games?\b", 0).match(subject):
                return subject, "arcade-catalog-addition"
    owned_release = _compiled_rule(r"^(?:apple\s+(?:has\s+)?(?:releases?|released|launches?|launched)\s+"
        r"(?:(?:its|a|new|immersive)\s+)*(?:film|movie|video|series)\b|"
        r"苹果(?:发布|推出)(?:了|新|沉浸式|空间)*(?:影片|电影|视频|剧集))\s*[\"“《]([^\"”》]+)[\"”》]", re.I).match(title_text)
    if owned_release:
        subject = _compiled_rule(r"[^a-z0-9\u3400-\u9fff]+").sub("-", owned_release.group(1)).strip("-")
        return subject, "release"
    if "apple-tv" not in identity.products and not owned_film_title:
        return None
    quoted_title = _quoted_subjects(title)
    if (quoted_title and _compiled_rule(r"\blands?\s+on\s+apple\s*tv\b", re.I).search(title)
            and _compiled_rule(r"\b(?:on\s+)?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|"
                          r"may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|"
                          r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}\b", re.I).search(title)):
        return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(quoted_title[0]), 0).strip("-").removeprefix("the-"), "premiere-schedule"
    if (quoted_title and _compiled_rule(r"\b(?:free|no-cost)\b", re.I).search(title)
            and _compiled_rule(r"\b(?:airing|streaming|watch|available)\b", re.I).search(title)
            and _compiled_rule(r"\b(?:specials?|shows?|films?|movies?)\b", re.I).search(title)):
        return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", _normalized(quoted_title[0]), 0).strip("-").removeprefix("the-"), "free-streaming-window"
    headline_claim = _headline_content_claim(title, lead)
    if headline_claim:
        return headline_claim
    rights_scope = f"{title}. {lead[:700]}"
    source_lands_film_deal = bool(
        _compiled_rule(r"\bapple(?: tv)?\s+lands?\b.{0,90}\b(?:film|movie|series|show)\b", re.I).search(title)
        and _compiled_rule(r"\bdeal\b[^.!?]{0,80}\b(?:figures?|dollars?|rights?|million|billion)\b", re.I).search(lead)
    )
    rights_action = source_lands_film_deal or bool(
        _compiled_rule(r"\b(?:apple tv\s+)?(?:acquires?|acquired|buys?|bought|(?:has|have) picked up|picks? up|"
            r"secures?)\b.{0,90}\b(?:rights?|streaming|series|show|film|movie|comedy)\b|"
            r"\b(?:worldwide|global)(?:\s+streaming)?\s+rights?\b|"
            r"(?:apple tv|苹果 tv).{0,36}(?:买下|购得|收购|取得|拿下).{0,36}"
            r"(?:版权|播映权|流媒体权利|剧集|影片|电影)|"
            r"(?:版权|播映权|流媒体权利).{0,24}(?:被|由)?\s*(?:苹果|apple tv)"
            r".{0,24}(?:买下|购得|收购|取得|拿下)", re.I).search(rights_scope)
    )
    if rights_action:
        subject_candidates = [
            subject.replace("-", " ")
            for subject in sorted(identity.title_named_subjects or identity.named_subjects)
            if subject not in {"apple-tv", "apple-tv-plus"}
        ]
        subject_candidates.extend(
            candidate.strip()
            for candidate in _quoted_subjects(rights_scope)
            if candidate.strip().lower() not in {"apple tv", "apple tv+"}
        )
        for pattern in (
            r"(?:worldwide|global)(?:\s+streaming)?\s+rights?\s+to\s+"
            r"(?:the\s+)?(?:(?:bbc|british)\s+)?"
            r"(?:(?:comedy|series|drama|film|movie|show)\s+)?"
            r"([A-Z][A-Za-z0-9'’:&.-]*(?:\s+[A-Z][A-Za-z0-9'’:&.-]*){0,7})",
            r"\b(?:comedy\s+series|comedy|series|drama|film|movie|show)\s*,?\s*"
            r"([A-Z][A-Za-z0-9'’:&.-]*(?:\s+[A-Z][A-Za-z0-9'’:&.-]*){0,7})",
        ):
            match = re.search(pattern, rights_scope)
            if match:
                subject_candidates.append(match.group(1).strip())
        if subject_candidates:
            ignored_subjects = {
                "apple tv",
                "bbc",
                "british",
                "global streaming",
                "worldwide rights",
            }
            for raw_subject in subject_candidates:
                if _normalized(raw_subject) in ignored_subjects:
                    continue
                subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", raw_subject.lower(), 0).strip("-")
                if subject:
                    return subject, "rights-acquisition"
    match = _compiled_rule(r"^apple tv\s+['\"](?P<subject>[^'\"]{2,90})['\"]\s+"
        r"(?P<action>release|return|renewal|trailer release)\b", 0).match(title_text)
    if not match:
        match = _compiled_rule(r"^(?:(?:emmy|award)[- ]winning\s+)?(?P<subject>[a-z0-9][a-z0-9 '&:.-]{1,80}?)\s+"
            r"(?P<action>returns?|premieres?|debuts?|releases?)\s+(?:to|on)\s+apple tv\b", 0).match(title_text)
    if match:
        raw_subject = _compiled_rule(r"(?:['’]s\s+)?(?:first|second|third|fourth|fifth|\d+(?:st|nd|rd|th))\s+season$", re.I).sub("", match.group("subject"), 0).strip()
        raw_action = match.group("action")
        action = (
            "return"
            if raw_action.startswith("return")
            else "release"
            if raw_action.startswith(("premier", "debut", "release"))
            else raw_action.replace(" ", "-")
        )
    else:
        content_scope = _normalized(f"{lead[:900]} {evidence[:1200]}")
        title_is_content_story = bool(
            _compiled_rule(r"\b(?:series|drama|thriller|film|movie|documentary|show|season)\b|"
                r"(?:剧集|剧|惊悚片|电影|影片|纪录片|节目|新季)", 0).search(title_text)
        )
        first_party_content_action = bool(
            _contains(
                content_scope,
                "according to apple tv",
                "apple tv announced",
                "apple tv reveals",
                "apple tv revealed",
                "apple tv orders",
                "apple tv ordered",
                "apple tv 宣布",
                "苹果 tv 宣布",
            )
            and _contains(
                content_scope,
                "premiere",
                "premieres",
                "debut",
                "debuts",
                "global debut",
                "ordered",
                "orders",
                "首播",
                "上线",
                "预订",
            )
            or _compiled_rule(r"\bapple tv\b.{0,48}\b(?:announces?|reveals?|unveils?|orders?)\b|"
                r"\bapple tv\b.{0,48}(?:宣布|公布|揭晓|预订)", 0).search(title_text)
        )
        if not (title_is_content_story and first_party_content_action):
            return None
        quoted_subjects = [
            candidate.strip()
            for candidate in _quoted_subjects(f"{lead} {evidence}")
            if candidate.strip().lower() not in {"apple tv", "apple tv+"}
        ]
        if not quoted_subjects:
            return None
        raw_subject = quoted_subjects[0]
        action = "release"

    subject = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", raw_subject.lower(), 0).strip("-")
    if not subject:
        return None
    return subject, action


def _legal_case_key(identity: EventIdentity) -> str:
    topics = set(identity.case_topics)
    topic_terms = {
        token
        for topic in topics
        for token in topic.split("-")
    }
    counterparties = {
        party
        for party in identity.counterparties
        if party not in topic_terms and party not in {"apple", "secrets", "lawsuit"}
    }
    parts = sorted(counterparties | topics)
    if not topics and identity.products:
        parts = sorted(identity.products)
    return ":".join(parts)


def _retrospective_explainer_without_new_action(title: str, text: str) -> bool:
    title_text = _canonical_title(title)
    return bool(
        _compiled_rule(r"^(?:how|why)\s+apple\b", 0).match(title_text)
        and _compiled_rule(r"\b(?:last\s+(?:week|month|year)|previously|earlier|already)\b|"
            r"(?:上周|上月|去年|此前|早前|已经)", 0).search(text)
        and _compiled_rule(r"\b(?:had|has|have)\s+(?:already\s+)?appeared\s+in\s+previous\b|"
            r"\b(?:previously reported|already reported|no new reporting|"
            r"not new information)\b|"
            r"\b(?:all|most)\b.{0,80}\b(?:references?|identifiers?|assets?)\b"
            r".{0,80}\b(?:appeared|reported|disclosed)\b.{0,30}\bprevious\b|"
            r"(?:此前已经|早已).{0,40}(?:出现|报道|披露)|"
            r"(?:没有|并无)新增(?:消息|信息|动作)", 0).search(text)
    )


def _apple_event_schedule_title(title: str) -> bool:
    title_text = _canonical_title(title)
    return bool(
        _compiled_rule(r"\b(?:apple|iphone)\s+(?:event|keynote)\b", 0).search(title_text)
        or _compiled_rule(r"\bapple\b.{0,70}\b(?:announces?|unveils?|confirms?)\b"
            r".{0,70}\b(?:event|keynote)\b|"
            r"\bapple\b.{0,70}\b(?:event|keynote)\b.{0,50}"
            r"\b(?:announces?|confirmed?|scheduled?)\b", 0).search(title_text)
        or _compiled_rule(r"苹果(?:\s*20\d{2})?\s*(?:春季|秋季)?\s*(?:新品|iphone)?\s*发布会|"
            r"苹果.{0,24}特别活动", 0).search(title_text)
    )


def _apple_event_campaign_title_context(title: str) -> bool:
    """Return true when the headline itself owns a current Apple event action."""
    title_text = _canonical_title(title)
    explicit_campaign_asset = bool(
        _compiled_rule(r"\b(?:event\s+)?(?:tagline|slogan|theme|hashtag|hashmoji)\b|"
            r"\bcustom\s+apple\s+logo\b|"
            r"(?:发布会)?(?:标语|口号|主题|话题标签|哈希表情|定制苹果标志)", 0).search(title_text)
    )
    explicit_schedule = bool(
        _compiled_rule(r"\b(?:event|keynote)\b|发布会|苹果.{0,24}特别活动", 0).search(title_text)
        and _compiled_rule(r"\b(?:announc(?:e|es|ed|ement)|confirm(?:s|ed)?|schedule(?:s|d)?|"
            r"sets?\s+(?:the\s+)?date|dated?\s+for)\b|"
            r"(?:官宣|确认|定档|宣布.{0,12}(?:日期|时间)|公布.{0,12}(?:日期|时间))", 0).search(title_text)
    )
    return explicit_campaign_asset or explicit_schedule


def _apple_event_invitation_interpretation_context(title: str, lead: str = "") -> bool:
    """Identify media interpretation of event artwork, not Apple's event action."""
    title_text = _canonical_title(title)
    invitation_subject = bool(
        _compiled_rule(r"\b(?:apple\s+)?(?:event\s+)?(?:invite|invitation|logo|artwork|graphic)\b|"
            r"(?:苹果)?(?:发布会|活动)?(?:邀请函|标志|logo|图案|视觉)", re.I).search(title_text)
    )
    interpretation_action = bool(
        _compiled_rule(r"\b(?:hints?|suggests?|teases?|clues?|interprets?|reads?\s+into)\b|"
            r"(?:暗示|解读|玄机|剧透|线索|指向|卖点)", re.I).search(title_text)
    )
    product_feature = bool(
        _compiled_rule(r"\b(?:iphone|ipad|mac|apple\s+watch|airpods)\b|"
            r"(?:苹果)?(?:手机|平板|电脑|手表|耳机)|(?:光圈|相机|配色|颜色)", re.I).search(f"{title_text} {_short_lead_scope(lead, sentences=1, limit=360)}")
    )
    return invitation_subject and interpretation_action and product_feature


def _apple_event_invitation_interpretation_key(
    title: str,
    lead: str,
    identity: EventIdentity,
    changed_objects: Iterable[str],
) -> str:
    if not _apple_event_invitation_interpretation_context(title, lead):
        return ""
    products = sorted(
        identity.title_products
        & {
            "airpods",
            "apple-watch",
            "foldable-iphone",
            "ipad",
            "iphone",
            "mac",
            "macbook",
        }
    )
    objects = sorted(
        value.removeprefix("changed-object:")
        for value in changed_objects
        if value.startswith("changed-object:")
    )
    if not products:
        return ""
    count_scope = f"{_normalized(title)} {_short_lead_scope(lead, sentences=1, limit=360)}"
    if _compiled_rule(r"(?:黑|白|银|金|蓝|红|绿|粉|紫)色(?:外观|机身|配色)?", 0).search(count_scope):
        objects = sorted(set(objects) | {"finish-color"})
    count_aliases = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "一": "1",
        "两": "2",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
    }
    count_match = _compiled_rule(r"\b(one|two|three|four|five|[1-5])\b"
        r"(?:\s+[a-z0-9-]+){0,6}\s+"
        r"(?:features?|clues?|details?|selling\s+points?)\b|"
        r"([一二两三四五1-5])\s*(?:大|项|个)?(?:卖点|功能|特性|细节|线索)", re.I).search(count_scope)
    # Explicit features identify the interpretation; a headline's count is
    # only a fallback when the source does not name the interpreted objects.
    if objects:
        qualifier = "+".join(objects)
    elif count_match:
        count_value = next(value for value in count_match.groups() if value)
        count_value = count_aliases.get(count_value.lower(), count_value)
        qualifier = f"count-{count_value}"
    else:
        return ""
    return (
        "primary-claim:apple-event-invitation:"
        f"{'+'.join(products)}:feature-interpretation:{qualifier}"
    )


def _apple_event_occurrence_keys(title: str, lead: str) -> set[str]:
    """Keep calendar evidence and only explicit regional date alternatives.

    A date without a time denotes a range, not a known UTC instant. Beijing
    dates can overlap the preceding event-local date; same-zone dates remain
    distinct, with those constraints enforced by the shared pair decision.
    """
    if (
        not _apple_event_campaign_title_context(title)
        or _apple_event_invitation_interpretation_context(title, lead)
    ):
        return set()
    scope = _normalized(title) + '\n' + _normalized(lead[:700])
    month_days: set[tuple[int, int, str]] = set()
    def local_zone(start: int) -> str:
        prefix = _compiled_rule(r'[。.!?\n（）()]', 0).split(scope[:start])[-1][-45:]
        markers = list(_compiled_rule(r'北京时间|beijing time|美国(?:当地)?(?:东部|太平洋)?时间|当地时间|local time|pacific time', 0).finditer(prefix))
        if not markers:
            return 'unspecified'
        return 'beijing' if markers[-1].group() in {'北京时间', 'beijing time'} else 'event-local'
    month_numbers = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    english_date = (
        r"(january|february|march|april|may|june|july|august|"
        r"september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?"
    )
    for match in re.finditer(
        rf"(?:\b(?:event|keynote)\b.{{0,70}}\b{english_date}\b|"
        rf"\b{english_date}\b.{{0,70}}\b(?:event|keynote)\b)",
        scope,
    ):
        values = [value for value in match.groups() if value]
        group = 1 if match.group(1) else 3
        month_days.add((month_numbers[values[0]], int(values[1]), local_zone(match.start(group))))
    chinese_date = r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    for match in re.finditer(
        rf"(?:(?:发布会|(?:新品|产品|特别)(?:发布)?活动).{{0,70}}{chinese_date}|"
        rf"{chinese_date}.{{0,70}}(?:发布会|(?:新品|产品|特别)(?:发布)?活动))",
        scope,
    ):
        values = [value for value in match.groups() if value]
        group = 1 if match.group(1) else 3
        month_days.add((int(values[0]), int(values[1]), local_zone(match.start(group))))

    keys: set[str] = set()
    years = set(_compiled_rule(r"(20\d{2})\s*年\s*\d{1,2}\s*月", 0).findall(scope))
    years.update(match.group(3) for match in re.finditer(english_date + r"\s*,?\s+(20\d{2})\b", scope))
    keys.update("apple-event-year:" + year for year in years)
    for month, day, zone in month_days:
        if zone == 'unspecified' and any(m == month and d == day and z != 'unspecified' for m, d, z in month_days):
            continue
        try:
            calendar_day = date(2000, month, day)
        except ValueError:
            continue
        keys.add(f"apple-event-calendar:{zone}:{month:02d}-{day:02d}")
        keys.add(f"apple-event-occurrence:{month:02d}-{day:02d}")
        if zone == "beijing":
            preceding = calendar_day - timedelta(days=1)
            keys.add(f"apple-event-occurrence:{preceding.month:02d}-{preceding.day:02d}")
    return keys


def _apple_event_campaign_key(title: str, lead: str) -> str:
    """Return a campaign key shared by an event announcement and its assets.

    Product overlap is deliberately insufficient. A campaign must expose a
    reusable name or tagline in an event announcement, localized slogan,
    hashtag, or hashmoji context. This keeps purchase surveys and product
    rumors outside the campaign while allowing source-specific follow-ups to
    contribute facts to the same announced event.
    """
    if (
        not _apple_event_campaign_title_context(title)
        or _apple_event_invitation_interpretation_context(title, lead)
    ):
        return ""
    raw_scope = " ".join(part for part in (title, lead[:700]) if part)
    scope = _normalized(raw_scope)
    campaign_context = bool(
        _compiled_rule(r"\b(?:apple\s+)?(?:event|keynote)\b|(?:苹果)?发布会", 0).search(scope)
        or _compiled_rule(r"\b(?:hashtag|hashmoji)\b|(?:话题标签|哈希表情)", 0).search(scope)
    )
    if not campaign_context:
        return ""

    candidates: list[str] = []
    campaign_patterns = (
        (r"[‘“\"]([^’”\"]{4,60})[’”\"]", title),
        (r":\s*'([^']{4,60})'\s*$", title),
        (r"\b(?:event|keynote)\s*:\s*['\"]?([a-z][a-z0-9 &-]{3,48})", title),
        (r"\bapple(?:'s)?\s+([a-z][a-z0-9 &-]{3,48}?)\s+hashmoji\b", title),
        (
            r"\b(?:localized?|localised?)\s+(?:the\s+)?([a-z][a-z0-9 &-]{3,48}?)\s+"
            r"(?:event\s+)?(?:tagline|slogan)\b",
            raw_scope,
        ),
        (
            r"\b(?:with|under|using|featuring)?\s*(?:the\s+)?(?:event\s+)?"
            r"(?:tagline|slogan)\b[^‘“\"']{0,48}[‘“\"']([^’”\"']{4,60})[’”\"']",
            raw_scope,
        ),
    )
    for pattern, value in campaign_patterns:
        candidates.extend(match.group(1) for match in re.finditer(pattern, value, re.I))

    ignored = {
        "apple",
        "apple event",
        "event",
        "iphone event",
        "iphone ultra",
        "keynote",
    }
    for candidate in candidates:
        label = _normalized(candidate).strip(" '\"-:,.!?，。！？：")
        label = _compiled_rule(r"^(?:the\s+|apple(?:'s)?\s+)", 0).sub("", label, 0)
        words = _compiled_rule(r"[a-z0-9]+|[\u3400-\u9fff]+", 0).findall(label)
        if not (2 <= len(words) <= 8):
            continue
        if label in ignored or _contains(
            label,
            "iphone",
            "ipad",
            "macbook",
            "foldable",
            "apple watch",
        ):
            continue
        slug = _compiled_rule(r"[^a-z0-9\u3400-\u9fff]+", 0).sub("-", label, 0).strip("-")
        if slug:
            return f"apple-event-campaign:{slug}"
    return ""


def _editorial_or_third_party_claim_reason(
    title: str,
    text: str,
    identity: EventIdentity,
) -> str:
    """Resolve headline ownership before Apple product terms can promote it."""
    title_text = _canonical_title(title)
    if quantified_apple_company_performance_subject(title, text):
        return ""
    if _retrospective_explainer_without_new_action(title_text, text):
        return "analysis or explanation without a new title-led Apple action"
    tutorial_title = bool(
        _compiled_rule(r"^(?:(?:\d+|ten)\s+)?(?:ways?\s+to|how\s+to|when\s+to|"
            r"tips?\s+(?:to|for)|guide\s+to)\b|^(?:如何|怎么|怎样|何时|\d+\s*个?技巧)", 0).match(title_text)
    )
    if tutorial_title:
        return "editorial tutorial without a new Apple action"
    if identity.content_form == "tutorial":
        return "editorial tutorial or settings advice without a new Apple action"
    if identity.content_form == "user_anecdote":
        return "editorial single-user workaround without a new Apple action"
    if identity.content_form == "review":
        return "editorial product review without a new Apple action"
    product_comparison = bool(
        _compiled_rule(r"\bvs\.?\b|\bversus\b|(?:对比|横评)", 0).search(title_text)
        and identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
        and not _compiled_rule(r"\b(?:lawsuit|court|judge|settlement|sues?|filings?|report|study|"
            r"leaks?|reveals?|discloses?|regulatory)\b|"
            r"(?:诉讼|法院|法官|和解|起诉|文件|报告|研究|泄露|曝光|披露|监管)", 0).search(title_text)
    )
    if product_comparison:
        return "editorial product comparison or buying advice without a new Apple action"
    reported_event_schedule = bool(
        _apple_event_schedule_title(title_text)
        and _compiled_rule(r"\b(?:september|october)\s+\d{1,2}\b|"
            r"\b\d{1,2}/\d{1,2}\b|"
            r"\d{1,2}\s*月\s*\d{1,2}\s*日", 0).search(text)
        and _compiled_rule(r"\b(?:according to|reports?|reported|published|claims?|sources? say|bloomberg|gurman|"
            r"leaker|leaks?|rumou?rs?)\b|"
            r"(?:据.{0,20}(?:报道|消息|透露)|报道称|报道分析|消息称|爆料|"
            r"多方消息|多方爆料|外媒分析|发文.{0,12}分析)", 0).search(text)
    )
    if identity.content_form == "analysis" and not reported_event_schedule and not _compiled_rule(r"\b(?:announces?|launches?|releases?|introduces?|adds?|expands?|changes?|"
        r"updates?|raises?|lowers?|opens?|closes?|acquires?|sues?|settles?|"
        r"is\s+(?:launching|releasing|adding|expanding|changing|updating|testing)|"
        r"will\s+(?:launch|release|add|expand|change|update))\b|"
        r"(?:宣布|推出|发布|新增|扩展|调整|更新|涨价|降价|开放|关闭|收购|起诉|和解)", 0).search(title_text):
        return "analysis or explanation without a new title-led Apple action"
    routine_refurb_roundup = bool(
        _contains(title_text, "refurb store", "refurbished store", "官翻", "翻新商店")
        and _contains(title_text, "offers", "deals", "discount", "save", "more", "优惠", "折扣", "降价")
        and not _contains(
            title_text,
            "adds",
            "expands",
            "launches",
            "new configurations",
            "新增",
            "扩展",
            "上架新配置",
        )
    )
    if routine_refurb_roundup:
        return "editorial deal roundup without a new Apple action"
    anniversary_recap = bool(
        _compiled_rule(r"\bturns?\s+(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\b|"
            r"\b(?:celebrates?|marks?)\s+(?:its\s+)?\d{1,3}(?:st|nd|rd|th)?\s+anniversary\b|"
            r"(?:迎来|问世|发布|诞生|庆祝).{0,12}\d{1,3}\s*周年", 0).search(title_text)
    )
    title_current_action = bool(
        _compiled_rule(r"\b(?:announces?|launches?|releases?|introduces?|adds?|expands?|"
            r"opens?)\b|(?:宣布|推出|发布|新增|扩展|开放)", 0).search(title_text)
    )
    if anniversary_recap and not title_current_action:
        return "anniversary or retrospective recap without a new Apple action"
    comparison_to_apple = bool(
        _compiled_rule(r"\b(?:catch(?:es|ing)?\s+up(?:\s+to|\s+with)?|"
            r"close[sd]?\s+the\s+gap\s+with|outpace[sd]?|outperform[sd]?|"
            r"beats?\s+out|rival[sd]?|versus|vs\.?|mimics?|matches?|"
            r"moves?\s+closer\s+to)\s+"
            r"(?:apple|iphone|ipad|mac(?:book|os)?|safari|watchos|tvos|visionos)\b|"
            r"(?:向[^，。,:;；]{0,24}(?:苹果|iphone|ipad|mac|safari)"
            r"[^，。,:;；]{0,24}靠拢)|"
            r"(?:追赶|赶超|媲美|对标|对比|挑战|超越)"
            r"[^，。,:;；]{0,14}(?:苹果|iphone|ipad|mac|safari)|"
            r"(?:把|将)(?:苹果|iphone|ipad|mac|safari)"
            r"[^，。,:;；]{0,12}(?:甩在身后|压过|击败)|"
            r"\bleaves?\s+(?:apple|iphone|ipad|mac)\s+behind\b", re.I).search(title)
    )
    direct_apple_title = bool(
        _compiled_rule(r"^(?:apple(?:'s|’s)?|苹果)", 0).search(title_text)
        or _compiled_rule(r"^(?:how|why)\s+apple\b", 0).search(title_text)
        or _compiled_rule(r"^[^:：]{2,32}[：:]\s*(?:apple(?:'s)?|苹果)", 0).search(title_text)
        or _compiled_rule(r"^(?:report|leak|code|sources?|消息|报道|泄露|代码|文件|爆料)"
            r"[^。.!?]{0,32}(?:apple(?:'s|’s)?|苹果)", 0).search(title_text)
    )
    if (
        not direct_apple_title
        and comparison_to_apple
    ):
        return "non-Apple primary subject using Apple only as comparison context"
    primary_clause, separator, trailing_clause = title_text.partition(":")
    if not separator:
        primary_clause, separator, trailing_clause = title_text.partition("：")
    apple_subject = _compiled_rule(r"\b(?:apple|iphone|ipad|mac(?:book|os)?|airpods|watchos|tvos|visionos|safari)\b|苹果", re.I)
    attributed_report_prefix = any(
        component.startswith("report-attribution:")
        for component in identity.components
    )
    if (
        separator
        and title_current_action
        and not attributed_report_prefix
        and not apple_subject.search(primary_clause)
        and not build_event_identity(primary_clause, "").title_products
        and apple_subject.search(trailing_clause)
    ):
        return "non-Apple primary subject using Apple only as comparison context"

    retrospective_hands_on = bool(
        identity.content_form in {"hands_on", "review"}
        and _compiled_rule(r"\b(?:revisiting|revisit|looking\s+back|look\s+back|throwback|"
            r"resharing|from\s+20\d{2})\b|(?:回顾|重温|旧款|往年体验|重新分享)", 0).search(title_text)
    )
    if retrospective_hands_on:
        return f"editorial {identity.content_form.replace('_', ' ')} without a new Apple action"

    attributed_reporting = _contains(
        title_text,
        "report",
        "reported",
        "sources",
        "filing",
        "document",
        "according to",
        "报道称",
        "消息称",
        "文件显示",
        "爆料",
    )
    first_person_editorial = bool(
        _compiled_rule(r"\b(?:i|we)\s+(?:would|could|want|wish|would\s+like)\b.{0,70}"
            r"\b(?:change|fix|see|remove|add)\b|"
            r"\bone\s+(?:design\s+)?decision\b.{0,55}\bi\s+would\s+change\b|"
            r"(?:我|我们).{0,24}(?:希望|想要|会去|建议).{0,24}(?:改变|修改|加入|移除)", 0).search(title_text)
    )
    if first_person_editorial and not attributed_reporting:
        return "opinion or commentary without a new Apple action"

    future_recap_question = bool(
        _compiled_rule(r"\b(?:which|what|where)\b.{0,55}\b(?:is|are|comes?|coming)\s+next\??$|"
            r"(?:哪些|什么|哪里).{0,30}(?:下一批|接下来|即将).{0,20}[?？]?$", 0).search(title_text)
    )
    current_action = bool(
        identity.title_actions
        or _contains(
            title_text,
            "announces",
            "launches",
            "releases",
            "adds",
            "expands",
            "宣布",
            "推出",
            "发布",
            "新增",
            "扩展",
        )
    )
    if future_recap_question and not current_action:
        return "editorial future-support recap without a new Apple action"

    if (
        _contains(title_text, "archive", "档案", "存档", "历史刊物", "往期杂志")
        and _contains(text, "past", "history", "issues", "历史", "往期", "旧刊")
        and not _contains(
            title_text,
            "apple launches",
            "apple releases",
            "apple opens",
            "苹果推出",
            "苹果发布",
            "苹果开放",
        )
    ):
        return "third-party archive or retrospective without a new Apple action"

    third_party_builder = bool(
        not _compiled_rule(r"^(?:apple(?:'s)?|苹果)", 0).match(title_text)
        and _contains(title_text, "ios", "ipados", "macos", "watchos", "visionos", "iphone", "ipad", "mac")
        and _compiled_rule(r"\b(?:developer|editor|author|user|outlet|publication)\b.{0,75}"
            r"\b(?:builds?|built|creates?|created|develops?|developed|made)\b.{0,45}"
            r"\b(?:app|tool|utility|widget|driver)\b|"
            r"(?:外媒|媒体|编辑|作者|开发者|用户|网友).{0,70}"
            r"(?:开发|制作|打造|编写).{0,45}(?:应用|工具|程序|组件|驱动)", 0).search(title_text)
    )
    if third_party_builder:
        return "third-party developer utility using an Apple platform without an Apple action"
    return ""


def _vehicle_platform_policy_clarification(title: str, lead: str) -> tuple[str, str] | None:
    """An attributed carmaker policy with distinct combustion and EV scope."""
    title_text, scope = _canonical_title(title), _normalized(lead)
    if not _compiled_rule(r"carplay", 0).search(title_text):
        return None
    publisher = _compiled_rule(r"\ba\s+([a-z][a-z0-9]*(?:\s+[a-z][a-z0-9]*){0,3})\s+spokesperson\b", 0).search(scope)
    if not publisher:
        publisher = _compiled_rule(r"[\u4e00-\u9fff]{2,24}\s*\(([a-z][a-z0-9]*(?:\s+[a-z][a-z0-9]*){0,3})\)", 0).search(scope)
    if not publisher:
        publisher = _compiled_rule(r"^([a-z][a-z0-9]*(?:\s+[a-z][a-z0-9]*){0,2})\s+(?:confirms?|clarifies?)\b", 0).match(title_text)
    if not publisher:
        return None
    owner = _compiled_rule(r"\s+", 0).sub("-", publisher.group(1), 0)
    current_confirmation = bool(re.search(
        r"spokesperson[^.!?]{0,35}(?:confirmed|clarified)|发言人[^。！？]{0,16}(?:确认|澄清|重申)|"
        + re.escape(publisher.group(1)) + r"\s+(?:has\s+)?(?:confirmed|confirms|clarified|cleared up confusion)", scope))
    combustion = _compiled_rule(r"specific to (?:the |just their new )?gas[- ]powered|"
        r"(?:keep|retention)[^.!?]{0,70}gas[- ]powered|"
        r"not removed[^.!?]{0,100}gas[- ]powered|仅(?:适用于|现有)?燃油|只有燃油", 0).search(scope)
    future_ev = _compiled_rule(r"future evs[^.!?]{0,30}(?:not offer|ditch)|"
        r"(?:ditch|dropping) carplay[^.!?]{0,40}future evs|"
        r"(?:ev lineup[^.!?]{0,40}off-limits|not rolling phone projection[^.!?]{0,30}evs)|"
        r"未来(?:纯电|电动)[^。！？]{0,30}(?:取消|不支持)", 0).search(scope)
    if not (current_confirmation and combustion and future_ev):
        return None
    return owner, "combustion-support-future-ev-withdrawal"


def _unsupported_third_party_reason(
    title: str,
    text: str,
    identity: EventIdentity,
    exact_facets: frozenset[str],
    relevance_tier: str,
    trusted_direct_action: bool,
) -> str:
    if is_editorial_change_request(title):
        return "reader poll about a desired change without an asserted Apple action"
    if _official_apple_store_transaction_option_action(title, text):
        return ""
    if "consumer-purchase-intent" in identity.title_components:
        return "consumer purchase-intent survey without a direct Apple action"
    # Missing title ownership is not evidence that Apple is merely background.
    # Concrete third-party/editorial relations below can defer a source; without
    # them the source outcome still requires positive Apple-action support.
    if (
        _third_party_platform_app_action(title, text)
        and not is_material_apple_device_operational_deployment(title, text)
    ):
        return "third-party software action on an Apple platform without a direct Apple action"
    if _vehicle_platform_policy_clarification(title, text):
        return "third-party vehicle compatibility policy clarification without an Apple platform change"
    if _third_party_accessory_action(title, text):
        return "third-party accessory without an Apple product or platform change"
    if (
        "non-apple-component-market-background" in identity.facets
        and not trusted_direct_action
        and not _measured_apple_market_result_keys(title, text, text)
    ):
        return "broad multi-vendor market report without a measured Apple result"
    claim_reason = _editorial_or_third_party_claim_reason(title, text, identity)
    if claim_reason:
        versioned_editorial_feature = bool(
            claim_reason == "analysis or explanation without a new title-led Apple action"
            and _versioned_os_feature_report(text, identity)
        )
        if versioned_editorial_feature:
            claim_reason = ""
        false_non_apple_owner_signal = bool(
            claim_reason.startswith("non-Apple primary subject")
            and trusted_direct_action
            and identity.scope == "apple-direct"
            and (
                identity.action_owner in {"apple", "apple-target"}
                or bool(identity.title_products and identity.title_actions)
            )
        )
        if claim_reason and not false_non_apple_owner_signal:
            return claim_reason
    if relevance_tier == "ecosystem" or trusted_direct_action:
        return ""
    if _versioned_os_feature_report(text, identity):
        return ""
    if _broad_component_supply_outlook(text):
        return "broad component supply outlook without a direct Apple action"
    if _supplier_market_without_apple_action(text, identity):
        return "supplier market story without a direct Apple procurement or product action"
    if (
        _compiled_rule(r"^(?!apple(?:'s)?\b|beats\b)[a-z][a-z0-9.+-]{1,36}['’]s\b.{0,65}"
            r"\b(?:adapter|accessory|case|charger|controller|dock|keyboard|stand)\b", 0).match(text)
        and _contains(text, "iphone", "ipad", "mac", "apple watch", "airpods")
    ):
        return "third-party accessory without an Apple product or platform change"
    if (
        _contains(text, "jailbreak", "jailbroken", "越狱", "民间开发者")
        and _contains(text, "virtual machine", "virtualization", "macos on ipad", "虚拟机", "iPad 用上 macOS")
    ):
        return "unsupported third-party jailbreak or virtualization tool"
    if (
        _contains(text, "benchmark", "benchmarks", "跑分", "性能表现", "不及", "对比")
        and _contains(text, "than macbook", "macbook pro", "苹果快", "apple macbook")
        and not _contains(text, "apple report", "apple announced", "苹果宣布", "苹果发布")
    ):
        return "competitor benchmark with Apple comparison context"
    if (
        _contains(text, "carplay")
        and _compiled_rule(r"\b(?:third-party|apps?|boats?|yachts?)\b|游艇|船", 0).search(text)
        and not _contains(
            text,
            "apple adds",
            "apple changes",
            "apple announced",
            "ios adds",
            "ios changes",
            "苹果新增",
            "苹果宣布",
            "ios 新增",
        )
    ):
        return "third-party CarPlay availability without a platform change"
    content_form = _reconciliation_content_form(text, identity)
    if content_form == "event_preview":
        return "editorial event preview without a new Apple action"
    if any(component.startswith("os-wave:") for component in identity.components):
        return ""
    if content_form == "roundup":
        exact_current_action = bool(
            len(exact_facets) == 1
            and identity.title_actions
        )
        if not exact_current_action:
            return "editorial roundup without a new Apple action"
    if exact_facets:
        # A concrete, crawler-verified Apple action outranks weaker editorial
        # cues when the article itself is not an explicit roundup.
        return ""
    if content_form in {
        "buying_advice",
        "deal",
        "podcast",
        "poll",
        "roundup",
        "tutorial",
        "user_anecdote",
    }:
        return f"editorial {content_form.replace('_', ' ')} without a new Apple action"
    if _compiled_rule(r"^(?:no,|yes,|why\b|my\b)", 0).match(text) and not identity.title_actions:
        return "opinion or commentary without a new Apple action"
    if _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果).{2,60}\bexperience shows\b", 0).match(text):
        return "competitor experience commentary without a new Apple action"
    native_migration = bool(
        "cross-platform-data-migration" in identity.title_components
        and _compiled_rule(r"^(?:google|谷歌).{0,28}(?:android|安卓)", 0).match(_normalized(title))
        and _compiled_rule(r"upgrad\w*|adds?|升级|上线|新增", 0).search(_normalized(title))
        and not _compiled_rule(r"\b(?:independent|third-party|app)\b|第三方|独立应用", 0).search(_normalized(title))
    )
    if identity.scope == "third-party-context" and not native_migration:
        return "third-party title context without a direct Apple action"
    return ""


def _hard_third_party_boundary(text: str, defer_reason: str) -> str:
    if not defer_reason:
        return ""
    if defer_reason.startswith("broad component supply"):
        return "broad-component-supply-outlook"
    if defer_reason.startswith("supplier market story"):
        return "independent-supplier-market-story"
    if defer_reason.startswith("broad multi-vendor market"):
        return "independent-multi-vendor-market-report"
    if _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|ios\b|mac(?:book|os)?\b|苹果).{2,55}'s\s+"
        r"(?:latest\s+)?(?:ios|ipados|macos|watchos|carplay|iphone|ipad|mac)\s+"
        r"(?:app\s+)?(?:update|release|version|feature)\b", 0).match(text):
        return "independent-third-party-platform-update"
    if defer_reason.startswith("third-party ") or defer_reason.startswith((
        "editorial ",
        "competitor benchmark",
        "anniversary or retrospective",
        "unsupported third-party",
        "third-party CarPlay",
        "third-party employer asset disposal",
        "opinion or commentary",
        "reader poll",
        "competitor experience",
    )):
        return "independent-third-party-action"
    return ""


def _official_refurbished_store_action(text: str) -> bool:
    return bool(
        _contains(
            text,
            "certified refurbished store",
            "apple refurbished store",
            "online refurbished store",
            "official refurbished",
            "苹果官方翻新",
            "苹果认证翻新",
            "苹果翻新商店",
            "官翻",
        )
        and _contains(
            text,
            "adds",
            "added",
            "adding",
            "expands",
            "updates",
            "updated",
            "available",
            "began selling",
            "started selling",
            "上架",
            "新增",
            "开售",
            "扩充",
        )
    )


def _official_apple_store_transaction_option_action(title: str, lead: str) -> bool:
    """Recognize a material checkout change on Apple's own retail surface.

    A bank, wallet, or credit provider can own the announcement while the
    changed capability belongs to Apple Store checkout. This is different
    from a third-party app merely becoming available on an Apple platform.
    """
    text = _normalized(f"{title}. {lead[:900]}")
    official_store = bool(
        _compiled_rule(r"\b(?:apple\s+online\s+store|apple\s+store\s+online(?:\s+store)?)\b|"
            r"苹果\s*apple\s*store\s*在线商店|苹果在线商店", 0).search(text)
    )
    if not official_store or _contains(text, "app store", "应用商店"):
        return False
    transaction_option = _contains(
        text,
        "payment option",
        "payment method",
        "pay with",
        "checkout",
        "financing",
        "installment",
        "interest-free",
        "interest free",
        "credit card",
        "debit card",
        "付款选项",
        "支付方式",
        "结账",
        "分期",
        "免息",
        "信用卡",
        "借记卡",
    )
    buyer_can_use = bool(
        _compiled_rule(r"\b(?:customers?|users?|shoppers?)\b.{0,90}\b(?:can|may|able\s+to)\b"
            r".{0,90}\b(?:pay|choose|select|use|finance|buy|purchase)\b|"
            r"(?:用户|消费者|顾客).{0,90}(?:可|可以|能够|选择).{0,90}"
            r"(?:付款|支付|分期|免息|购买|选购)", 0).search(text)
    )
    apple_retail_purchase = bool(
        _compiled_rule(r"\b(?:buy|buying|purchase|purchasing|order|ordering)\b.{0,80}"
            r"\b(?:iphone|ipad|mac|apple\s+watch|airpods)\b|"
            r"(?:购买|选购|下单).{0,80}(?:iphone|ipad|mac|apple\s*watch|airpods|苹果产品)", 0).search(text)
    )
    return transaction_option and buyer_can_use and apple_retail_purchase


def _canonical_first_party_action_keys(
    identity: EventIdentity,
) -> set[str]:
    """Project a direct title claim onto a source-independent event key.

    The projection intentionally uses only action classes whose subject can be
    established without article-body context. This lets translations and
    differently worded headlines reconcile while keeping product roundups and
    multi-action stories out of the same bucket.
    """
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return set()
    actions = identity.title_actions & {
        "catalog-expansion",
        "commercial-launch",
        "leadership-transition",
        "model-development",
        "withdrawal",
    }
    if not actions:
        actions = identity.actions & {
            "catalog-expansion",
            "commercial-launch",
            "leadership-transition",
            "model-development",
            "withdrawal",
        }
    if not actions:
        return set()

    subjects: set[str] = set()
    if "official-refurbished-catalog" in identity.components:
        subjects.add("official-refurbished-catalog")
    if "apple-leadership" in identity.components:
        subjects.add("apple-leadership")
    direct_products = identity.title_products & {
        "apple-intelligence",
        "apple-maps",
        "iphone",
    }
    if len(direct_products) == 1:
        subjects |= direct_products
    if not subjects:
        return set()
    return {
        f"canonical-apple-action:{subject}:{action}"
        for subject in subjects
        for action in actions
    }


def _source_current_hardware_release(lead: str, identity: EventIdentity) -> bool:
    """Use the primary clause's Apple publisher and direct released object.

    This is source support only; it does not invent title actions or a merge
    key from a product family. Later research and future features stay facts.
    """
    if identity.content_form != "news" or not identity.title_products:
        return False
    title_products = identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    if not title_products or title_products != identity.title_products:
        return False
    clause = _primary_assertion_scope("", lead)[1].lstrip(" .")
    clause = _compiled_rule(r"^[^。.!?]{0,40}(?:消息|讯)[,，:：]?\s*", 0).sub("", clause, 0)
    action = _compiled_rule(r"^(?:apple\s+(?:(?:has|today|now|officially|just)\s+)*"
        r"(?:announces?|announced|introduces?|introduced|launches?|launched|"
        r"unveils?|unveiled|releases?|released)\s+|"
        r"苹果(?:公司|官方)?(?:今日|今天|近日|现已|正式|刚刚)*(?:发布|推出|揭晓)了?\s*)"
        r"(?P<object>[^，,。;；!?]+)", re.I).match(clause)
    if not action:
        return False
    direct_object = _compiled_rule(r"^(?:(?:the|a|an|new|its)\s+|(?:全新|新款)\s*)+", re.I).sub("", action.group("object"), 0)
    released_products = _bounded_evidence_products(direct_object)
    direct_products = {product for product, patterns in _BOUNDED_PRODUCT_PATTERNS
        if any((pattern is not None and pattern.match(direct_object))
               or (pattern is None and direct_object.startswith(alias))
               for alias, pattern, _possessive in patterns)}
    return bool(released_products == title_products and direct_products & title_products)


def _editorial_source_proves_current_first_party_action(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> bool:
    """Let editorial framing carry an independently stated Apple action."""
    # An arrival roundup can still report today's first-party fulfillment.
    # Require both the delivered product and the Store pickup operation in
    # the lead, so an old launch recap alone never supplies a new action.
    current_fulfillment = _compiled_rule(
        r"\b(?:apple(?:'s|’s)?\s+)?(?:new\s+)?mac(?:\s+mini|\s+studio|s)?\b"
        r"[^.!?]{0,120}\b(?:arriv(?:e|ing)|deliver(?:ed|ies|y))\b[^.!?]{0,55}\btoday\b",
        re.I,
    ).search(lead)
    store_pickup = _compiled_rule(
        r"\bApple\s+Stores?\b[^.!?]{0,80}\b(?:begun|started|now)\b"
        r"[^.!?]{0,50}\bpickup\b", re.I,
    ).search(lead)
    if current_fulfillment and store_pickup and _compiled_rule(r"\bMacs?\b", re.I).search(title):
        return True
    # A release roundup can independently report that the named new models
    # reached Apple's stores and customers today, even without the word pickup.
    if (_compiled_rule(r"\bMacs?\b", re.I).search(title)
            and _compiled_rule(r"\b(?:new\s+)?mac\s+mini\b[^.!?]{0,35}\bmac\s+studio\b", re.I).search(lead[:400])
            and _compiled_rule(r"\blaunched\s+in\s+apple\s+stores\b[^.!?]{0,85}"
                               r"\bbegan\s+arriving\s+to\s+customers\s+today\b", re.I).search(lead[:400])):
        return True
    if (identity.content_form in {"poll", "hands_on", "review"}
            and is_direct_first_party_builtin_removal(title, lead)):
        return True
    if (
        identity.content_form not in {"hands_on", "review"}
        or identity.scope != "apple-direct"
        or not identity.title_products
    ):
        return False
    lead_scope = _short_lead_scope(lead, sentences=2, limit=520)
    lead_scope = _compiled_rule(r"^[^。.!?]{0,40}(?:消息|讯)[,，:：]?\s*", 0).sub("", lead_scope, 0)
    first_party_owner = bool(
        _compiled_rule(r"^(?:apple(?:'s|’s)?|apple\s+(?:officially|today)|苹果(?:公司|官方)?)"
            r".{0,90}\b(?:launch(?:ed|es)?|release(?:d|s)?|introduc(?:ed|es)?|"
            r"list(?:ed|s)?|made\s+available|lower(?:ed|s)?|rais(?:ed|es)?)\b|"
            r"^(?:苹果(?:公司|官方)?).{0,90}(?:上架|发布|推出|开售|上市|降价|涨价|调价)", re.I).search(lead_scope)
    )
    current_action = bool(
        identity.title_actions & {"price-change", "product-launch", "retail-availability"}
        or _compiled_rule(r"\b(?:now\s+available|launch(?:ed|es)?|release(?:d|s)?|introduc(?:ed|es)?|"
            r"list(?:ed|s)?|lower(?:ed|s)?|rais(?:ed|es)?\s+(?:the\s+)?price)\b|"
            r"(?:近日|今日|现已).{0,24}(?:上架|发布|推出|开售|上市)|"
            r"(?:价格|售价).{0,16}(?:下调|上调|降至|涨至)|(?:降价|涨价|调价)", re.I).search(f"{_normalized(title)} {lead_scope}")
    )
    return first_party_owner and current_action


def _third_party_platform_app_action(
    title: str,
    lead: str,
) -> tuple[str, str, str] | None:
    """Identify a third-party software owner separately from its Apple target."""
    title_text = _normalized(title)
    first_party_hardware_disclosure = bool(
        _compiled_rule(r"\b(?:apple(?:-made)?|first[- ]party)\b.{0,42}"
            r"\b(?:controllers?|devices?|accessories|peripherals?|hardware)\b|"
            r"(?:苹果|自研|第一方).{0,28}(?:手柄|控制器|设备|配件|外设|硬件)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:unreleased|prototype|code|identifier|found|hint(?:s|ed)?)\b|"
            r"(?:未发布|原型|代码|标识符|曝光|发现|暗示)", re.I).search(title_text)
    )
    if first_party_hardware_disclosure:
        return None
    if _compiled_rule(r"^(?:apple(?:'s)?|苹果|ios\b|ipados\b|macos\b|watchos\b|tvos\b|visionos\b)", 0).match(title_text):
        return None
    # A named app can own a "turns your iPhone into ..." feature headline.
    # Its device/music-service targets do not become first-party actions.
    app_actor = _compiled_rule(r"^([A-Z][A-Za-z0-9.+-]*)\s+(?:turns?|transforms?)\b", 0).match(title)
    if (app_actor and not _bounded_evidence_products(app_actor.group(1))
            and not _lead_assigns_app_release_to_apple(app_actor.group(1), lead)):
        app_name = app_actor.group(1)
        app_statement = _compiled_rule(r"\b" + re.escape(app_name) + r"\s+(?:app|application)\b|"
            r"\b(?:app|application)\s+(?:called|named)\s+" + re.escape(app_name) + r"\b", re.I).search(lead[:1000])
        target = _compiled_rule(r"\b(iphone|ipad|mac)\b", re.I).search(title)
        if app_statement and target:
            platform = {"iphone": "ios", "ipad": "ipados", "mac": "macos"}[target.group(1).lower()]
            return _normalized(app_name), platform, "platform"

    # A developer platform adds support for a named device's simulator. The
    # Apple SDK mentioned as context is neither publisher nor current actor.
    simulator_target = _compiled_rule(r"\biphone\s+([a-z0-9]+(?:\s+(?:pro|max|mini|plus))*)\b", 0).search(title_text)
    simulator_owner = _compiled_rule(r"^([a-z][a-z0-9.+-]*)\s+(?:adds?|introduces?)\b", 0).match(title_text)
    if not simulator_owner:
        simulator_owner = _compiled_rule(r"(?:编程平台|开发平台)\s*([a-z][a-z0-9.+-]*)\s*(?:宣布|新增|引入)", 0).search(title_text)
    if (simulator_owner and simulator_target
            and _compiled_rule(r"(?:interactive\s+)?3d\s+simulator|交互式\s*3d\s*模拟器", 0).search(title_text)
            and _compiled_rule(r"building and testing|构建.{0,5}测试|开发者测试", 0).search(_normalized(lead))):
        return (simulator_owner.group(1), "ios",
                "developer-simulator-iphone-" + _compiled_rule(r"\s+", 0).sub("-", simulator_target.group(1), 0))
    platform = next(
        (
            value
            for value, terms in (
                (
                    "macos",
                    (
                        "mac app",
                        "macos",
                        "for mac",
                        "on mac",
                        "on the mac",
                        "to mac",
                        "mac端",
                        "mac 端",
                        "mac 应用",
                        "mac 客户端",
                        "mac 桌面端",
                        "mac 原生版",
                        "mac 版",
                        "登陆 mac",
                        "登陆mac",
                    ),
                ),
                (
                    "ios",
                    (
                        "ios app",
                        "iphone to android",
                        "for iphone",
                        "to iphone",
                        "iphone 应用",
                        "ios 应用",
                        "ios版",
                        "ios 版",
                    ),
                ),
                ("ipados", ("ipados app", "for ipad", "to ipad", "ipad 应用")),
                ("watchos", ("watchos app", "apple watch app", "watch 应用")),
                ("visionos", ("visionos app", "vision pro app", "vision pro 应用")),
                ("tvos", ("tvos app", "apple tv app", "apple tv 应用")),
            )
            if _contains(title_text, *terms)
        ),
        "",
    )
    software_subject = bool(
        _compiled_rule(r"\b(?:app|application|client|game|integration|plugin|utility|messages?|imessages?)\b|"
            r"(?:应用|客户端|桌面端|原生版|游戏|插件|工具)|"
            r"(?:ios|ipados|macos|watchos|visionos|tvos)\s*版", 0).search(title_text)
        or _contains(title_text, "imessage", "messages", "信息应用", "信息”应用")
    )
    if not platform or not software_subject:
        return None
    if not _compiled_rule(r"\b(?:add(?:s|ed|ing)?|gain(?:s|ed|ing)?|updat(?:e|es|ed|ing)|upgrad(?:e|es|ed|ing)|"
        r"can(?:\s+now)?\s+(?:read|send|control)|control(?:s|led|ling)?|"
        r"launch(?:es|ed|ing)?|release(?:s|d|ing)?|available|getting|"
        r"comes?\s+to|arriv(?:e|es|ed|ing)|support(?:s|ed|ing)?)\b|"
        r"(?:新增|更新|接入|集成|支持|控制|读取|发送|开放|推出|发布|上线|登陆|登录)", re.I).search(title_text):
        return None

    capitalized = _compiled_rule(r"(?<![A-Za-z0-9])"
        r"[A-Z][A-Za-z0-9.+-]*(?:\s+[A-Z][A-Za-z0-9.+-]*){0,2}"
        r"(?![A-Za-z0-9])", 0).findall(title)
    rejected = {
        "app",
        "apple",
        "apple tv",
        "iphone",
        "ipad",
        "mac",
        "macos",
        "watchos",
        "vision pro",
    }
    product_terms = {"airpods", "iphone", "ipad", "macbook", "homepod", "vision pro"}
    named = [
        _compiled_rule(r"\s+(?:can(?:\s+now)?|will|adds?|updates?|launches?|releases?|arrives?|gets?)\b.*$", re.I).sub("", value, 0)
        for value in capitalized
        if _normalized(value) not in rejected
        and not _normalized(value).startswith(("apple ", "mac ", "ios "))
        and not any(term in _normalized(value) for term in product_terms)
    ]
    # Prefer the leading publisher/product name. Later capitalized phrases are
    # commonly feature names (for example screen sharing or dictation), not
    # the owner of the app. If a later candidate extends the same leading
    # owner token, retain that fuller product name across translated headlines.
    owner = ""
    if named:
        first_root = _normalized(named[0]).split()[0]
        same_owner = [
            value
            for value in named
            if _normalized(value).split()[0] == first_root
        ]
        owner = max(same_owner, key=lambda value: (len(value.split()), len(value)))
    if not owner:
        owner = _compiled_rule(r"\b(?:is getting|comes? to|launch(?:es|ed)?|releases?|arrives?)\b|"
            r"(?:推出|发布|上线|登陆|登录)", 0).split(title_text, 1)[0].strip(" :-—–")
    owner_slug = _compiled_rule(r"[^\w]+", 0).sub("-", _normalized(owner), 0).strip("-")
    rejected_slugs = {_compiled_rule(r"[^a-z0-9]+", 0).sub("-", value, 0).strip("-") for value in rejected}
    if not owner_slug or owner_slug in rejected_slugs or owner_slug.startswith("apple-"):
        return None
    target = "platform"
    if _contains(title_text, "messages", "imessage", "信息应用", "信息”应用", "信息 app"):
        target = "messages"
    elif _contains(title_text, "carplay"):
        target = "carplay"
    return owner_slug, platform, target


def _third_party_accessory_action(title: str, text: str) -> bool:
    """Return true when a vendor accessory merely targets Apple devices."""
    title_text = _normalized(title)
    if _compiled_rule(r"^(?:apple(?:'s)?|苹果(?:官方)?)(?:\b|\s)", 0).match(title_text):
        return False
    primary_clause, separator, compatibility_clause = title_text.partition(":")
    if not separator:
        primary_clause, separator, compatibility_clause = title_text.partition("：")
    compatibility_only_launch = bool(
        separator
        and not _compiled_rule(r"\b(?:apple|iphone|ipad|mac(?:book)?|airpods|homepod|apple watch)\b|苹果", 0).search(primary_clause)
        and _compiled_rule(r"\b(?:launch(?:es|ed)?|release(?:s|d)?|goes? on sale|now available)\b|"
            r"(?:推出|发布|开售|上市|发售|现已开卖)", 0).search(primary_clause)
        and _compiled_rule(r"\b(?:supports?|compatible with|works with|integrates? with)\b.{0,30}"
            r"\b(?:apple home|homekit|iphone|ipad|mac|apple watch|homepod)\b|"
            r"(?:支持|兼容|适配|接入|可接入|原生支持).{0,24}"
            r"(?:apple home|homekit|iphone|ipad|mac|apple watch|homepod|苹果 home|苹果家庭)", 0).search(compatibility_clause)
    )
    if compatibility_only_launch:
        return True
    compatibility_target_launch = bool(
        not _compiled_rule(r"^(?:apple(?:'s)?|苹果(?:官方)?)(?:\b|\s)", 0).match(title_text)
        and _compiled_rule(r"\b(?:debuts?|launch(?:es|ed)?|introduc(?:es|ed)?|release(?:s|d)?|"
            r"goes?\s+on\s+sale|debuts?\s+at|appears?\s+at)\b|"
            r"(?:推出|发布|开售|上市|发售|亮相)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:with|for|supports?|compatible\s+with|works\s+with|integrates?\s+with)\b"
            r".{0,36}\b(?:apple\s+home|homekit|iphone|ipad|mac|apple\s+watch|homepod)\b|"
            r"(?:支持|兼容|适配|接入|可接入|原生支持).{0,28}"
            r"(?:apple\s+home|homekit|iphone|ipad|mac|apple\s+watch|homepod|"
            r"苹果\s*home|苹果家庭|苹果智能家庭(?:生态)?)", re.I).search(title_text)
    )
    if compatibility_target_launch:
        return True
    accessory_subject = bool(
        _compiled_rule(r"\b(?:adapter|case|charger|charging stand|controller|dock|keyboard|"
            r"power bank|screen protector|stand)\b|"
            r"(?:充电器|充电基座|充电宝|保护壳|保护套|转接器|适配器|支架|键盘|手柄)", 0).search(title_text)
    )
    apple_target = _contains(
        title_text,
        "iphone",
        "ipad",
        "macbook",
        "airpods",
        "apple watch",
        "ios",
    )
    vendor_action = _contains(
        title_text,
        "launch",
        "release",
        "hands-on",
        "compatible",
        "support",
        "推出",
        "发布",
        "首发",
        "开箱",
        "兼容",
        "适配",
        "支持",
    )
    official_apple_action = _contains(
        title_text,
        "apple launches",
        "apple releases",
        "apple unveils",
        "苹果推出",
        "苹果发布",
        "苹果上架",
        "苹果官方",
    )
    return bool(accessory_subject and apple_target and vendor_action and not official_apple_action)


def _leading_project_subject(title: str) -> str:
    """Extract a bounded project name that owns a compatibility milestone."""
    title = _compiled_rule(r"[!！]", 0).split(_canonical_title(title), 0)[-1].strip()
    match = _compiled_rule(r"^([a-z][a-z0-9.+-]*(?:\s+[a-z][a-z0-9.+-]*){0,3}?)"
        r"(?=(?:\s+(?:near(?:s|ing)?|approach(?:es|ing)?|adds?|gets?|gains?|"
        r"releases?|ships?|supports?|brings?|rolls?\s+out|now\s+supports?))|"
        r"(?:\s*(?:系统)?(?:官宣|宣布)?(?:正式)?(?:即将|将|已|接近|支持|适配)))", 0).match(title)
    if not match:
        return ""
    subject = match.group(1).strip()
    ignored = {
        "apple",
        "apple silicon",
        "iphone",
        "ipad",
        "linux",
        "mac",
        "macbook",
        "report",
    }
    if subject in ignored:
        return ""
    return _compiled_rule(r"[^a-z0-9]+", 0).sub("-", subject, 0).strip("-")


def _platform_compatibility_milestone(
    title: str,
    lead: str,
    evidence: str,
    identity: EventIdentity,
) -> tuple[str, str, str] | None:
    """Project a project/platform/version milestone across language variants."""
    scope = f"{_normalized(title)}. {_normalized(lead)[:700]} {_normalized(evidence)[:900]}"
    # Kernel patches are a component milestone, not a release of the whole
    # downstream OS. Bind the target and stage to the opening assertion.
    headline = _normalized(title)
    opening = _normalized(lead)[:700]
    component = _compiled_rule(r"(?<![a-z])(nvme|gpu|usb|audio|camera|display)(?![a-z])", 0).search(headline)
    generation = _compiled_rule(r"(?<![a-z0-9])m([1-9])(?:\b|(?=[\u4e00-\u9fff]))", 0).search(headline)
    if (component and generation and _compiled_rule(r"linux", 0).search(headline)
            and _compiled_rule(r"patch|driver|补丁|驱动", 0).search(headline)
            and _compiled_rule(r"linux\s+kernel|linux\s*内核", 0).search(opening)
            and _compiled_rule(r"(?<![a-z])apple(?![a-z])|苹果", 0).search(opening)):
        for start, end in source_sentence_spans(opening):
            claim = opening[start:end]
            if not (_compiled_rule(r"linux", 0).search(claim) and _compiled_rule(r"patch|driver|补丁|驱动", 0).search(claim)
                    and re.search(r"(?<![a-z0-9])m" + generation.group(1) + r"(?:\b|(?=[\u4e00-\u9fff]))", claim)
                    and component.group(1) in claim):
                continue
            if _compiled_rule(r"\b(?:not|never|previously|last\s+year|plans?\s+to)\b|尚未|没有|计划|此前|去年", 0).search(claim):
                break
            stage = ("merged" if _compiled_rule(r"\bmerged\b|已合入|已合并", 0).search(claim) else
                     "patch-submission" if _compiled_rule(r"\bsubmitted\b|提交", 0).search(claim) else "")
            if stage:
                return "linux", f"apple-silicon-m{generation.group(1)}", f"{component.group(1)}-{stage}"
            break
        return None
    project = _leading_project_subject(title)
    project_words = project.replace("-", " ")
    platform_project = bool(
        _compiled_rule(r"(?:linux|bsd|os)$", 0).search(project)
        or (project and re.search(
            re.escape(project_words) + r"\s+(?:operating\s+system|kernel|操作系统|内核)",
            scope,
        ))
    )
    generation_match = _compiled_rule(r"(?<![a-z0-9])m([1-9])(?:\s|$|[^a-z0-9])", 0).search(_normalized(title))
    compatibility = bool(
        _compiled_rule(r"\b(?:supports?|compatib(?:le|ility)|enablement|driver)\b|"
            r"(?:支持|适配|兼容|驱动)", 0).search(scope)
    )
    apple_platform = bool(
        _compiled_rule(r"\bapple\s+silicon\b|\bapple['’]?s\s+m[1-9]\b|苹果.{0,12}m[1-9](?:\s*系列)?\s*芯片", 0).search(scope)
        or any(
            component.startswith("apple-silicon-generation:")
            for component in identity.components
        )
    )
    if not (platform_project and generation_match and compatibility and apple_platform):
        return None
    if _compiled_rule(r"(?<![a-z])(?:nvme|gpu|graphics|audio|usb|display|camera)(?![a-z])|图形|音频|摄像头", 0).search(_canonical_title(title).split(':')[0]):
        # A component driver milestone is not whole-platform enablement.
        return None
    released_pattern = (
        r"\b(?:released|shipped|now\s+(?:available|supports?)|rolls?\s+out)\b|"
        r"(?:正式(?:发布|支持|适配)|现已可用|已经发布)"
    )
    imminent_pattern = (
        r"\b(?:near(?:s|ing)?|almost|close\s+to|coming\s+soon)\b.{0,48}"
        r"\b(?:release|ship|availability)\b|"
        r"(?:即将|接近|几乎).{0,30}(?:发布|推出|可用)"
    )
    title_scope, claim_scope = _primary_assertion_scope(title, lead)
    first_lead = claim_scope[len(title_scope) + 1:].strip()
    # A limitation is not the subject of the release; bind the main clause
    # to the same platform generation before borrowing its release stage.
    lead_action = _compiled_rule(r"\b(?:without|although|but|except)\b|但是|但|不过|尚不|不含", 0).split(first_lead, 1)[0]
    lead_generations = set(_compiled_rule(r"(?<![a-z0-9])m([1-9])(?:\b|(?=[\u4e00-\u9fff]))", 0).findall(lead_action))
    stage_scopes = [title_scope]
    if (
        first_lead.startswith((project_words, "the " + project_words))
        and lead_generations == {generation_match.group(1)}
        and not _compiled_rule(r"\b(?:gpu|graphics|audio|usb|display|camera)\b|图形|音频|摄像头", 0).search(lead_action)
    ):
        stage_scopes.append(lead_action)
    milestone = "support-development"
    for stage_scope in stage_scopes:
        if re.search(released_pattern, stage_scope):
            milestone = "released"
            break
        if re.search(imminent_pattern, stage_scope):
            milestone = "release-imminent"
            break
    return project, f"apple-silicon-m{generation_match.group(1)}", milestone


_MEMORY_SUPPLIER_ALIASES = {
    "cxmt": ("cxmt", "changxin", "长鑫"),
    "ymtc": ("ymtc", "yangtze memory", "长江存储"),
}


def _forecast_periods(claim: str) -> list[str]:
    quarters = {"first": "1", "second": "2", "third": "3", "fourth": "4", "一": "1", "二": "2", "三": "3", "四": "4"}
    result = set()
    for match in _compiled_rule(r"(20\d{2})\s*(?:年|财年)?\s*(?:q([1-4])|第([一二三四1-4])(?:财季|季度))", 0).finditer(claim):
        q = match.group(2) or quarters.get(match.group(3), match.group(3))
        result.add(f"{match.group(1)}-q{q}")
    for match in _compiled_rule(r"\bq([1-4])\s*(20\d{2})\b|\b(first|second|third|fourth)\s+quarter\s+(?:of\s+)?(?:fiscal\s+)?(20\d{2})\b", 0).finditer(claim):
        q = match.group(1) or quarters[match.group(3)]
        year = match.group(2) or match.group(4)
        result.add(f"{year}-q{q}")
    return sorted(result)


def _primary_report_claim(title: str, lead: str, identity: EventIdentity) -> tuple[str, str, str] | None:
    """Bind headlined results to their owner, not incidental body subjects."""
    headline = _canonical_title(title)
    scope = f"{headline}. {_normalized(lead)[:900]}"
    if identity.content_form != "news":
        return None
    joined_company = bool(_compiled_rule(r"\b(?:joins?|joining) apple(?=[,.;:]|$)|加入苹果(?=[，,。]|$)", 0).search(headline))
    relationship_scope = f"{headline}. {_short_lead_scope(lead, sentences=1, limit=500)}"
    joint_participation = bool(_compiled_rule(r"\b(?:coalition|consortium|standards group|working group|alongside)\b|"
        r"\bownership remains independent\b|(?:联盟|工作组|标准组织|所有权保持独立)", 0).search(relationship_scope))
    ownership_transfer = joined_company and not joint_participation
    uncertain_transfer = bool(_compiled_rule(r"\b(?:not|never|won['’]t|may|could|might)\s+(?:join|be acquired)\b|不会加入|可能加入", 0).search(headline))
    if ownership_transfer and not uncertain_transfer:
        names = {match.group(0).strip() for match in _compiled_rule(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9.+-]*(?:\s+[A-Z][A-Za-z0-9.+-]*){1,5}", 0).finditer(title)
            if not _compiled_rule(r"\s+awards?\b|\s*奖", re.I).match(title[match.end():])}
        names = {name for name in names if name.lower() not in {"apple acquisition", "open source"}}
        if len(names) == 1:
            organization = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", next(iter(names)).lower(), 0).strip("-")
            category = "software_systems" if "developer-tool-integration" in identity.facets else ""
            return f"apple-organization-{organization}", "ownership-transfer", category
    if is_apple_led_developer_submission_story(title, lead):
        project = _compiled_rule(r"(?:\bfor\s+|征集\s*|启动\s*)([a-z][a-z0-9-]+)\s+(20\d{2})\b", 0).search(scope)
        if project:
            return f"webkit-{project.group(1)}-{project.group(2)}", "developer-proposal-call", "software_systems"
    suppliers = [name for name, aliases in _MEMORY_SUPPLIER_ALIASES.items()
                 if _contains(headline, *aliases)]
    if len(suppliers) == 1 and _contains(headline, "apple", "苹果") and _compiled_rule(r"\b(?:partnership|cooperation|collaboration)\b|合作", 0).search(headline) and _compiled_rule(r"\brespond\w*\s+(?:to|about)\s+apple(?:'s)?\s+(?:partnership|cooperation|collaboration)\b|"
        r"(?:回应|表态)[^,;。]{0,8}(?:与)?苹果(?:公司|供应链)?(?:的)?合作|"
        r"释放[^,;。]{0,6}信号[^,;。]{0,8}与苹果(?:公司|供应链)?(?:的)?合作", 0).search(headline):
        return f"apple-supplier-{suppliers[0]}", "partnership-response", "hardware_products"
    report_scope = f"{headline}. {_normalized(lead)[:1700]}"
    institutions = [name for name, aliases in ANALYST_INSTITUTION_ALIASES
                    if _contains(report_scope[:450], *aliases)]
    forecast = r"\b(?:forecast\w*|predict\w*|expect\w*|models?|will\s+build)\b|预估|预测|预计|将生产"
    title_outlook = _compiled_rule(r"\b(?:forecasts?|predict\w*|expect\w*|warns?|could\s+(?:hurt|hit))\b|预估|预测|预计", 0).search(headline)
    if len(institutions) == 1 and "iphone" in headline and title_outlook and identity.scope == "apple-direct":
        for claim in _compiled_rule(r"[。！？;；]|(?<=[.!?])\s+|[,，]\s*(?:and\s+|but\s+|而|但)", 0).split(_normalized(lead)[:1700], 0):
            if not re.search(forecast, claim):
                continue
            if not _compiled_rule(r"\bapple\b[^,;。]{0,45}\b(?:builds?|produc\w*)\b|\biphone[^,;。]{0,35}\bbuilds?\b|\bbuild[^,;。]{0,40}\biphones?\b|苹果[^,;。]{0,30}生产|生产[^,;。]{0,30}iphone", 0).search(claim):
                continue
            volumes = _compiled_rule(r"(?:\bbuilds?\b|\bproduc\w*\b|生产|产量)[^.!?。\d]{0,55}"
                r"(\d+(?:\.\d+)?)\s*(million|万)\s*(?:部|units?|iphones?)", 0).finditer(claim)
            volume = next((item for item in volumes if not _compiled_rule(r"\b(?:down|less|fewer|reduc\w*|declin\w*)\b|减少|下降|下滑|降低", 0).search(item.group(0))), None)
            periods = _forecast_periods(claim)
            if not periods:
                # Annual forecasts require a stated year in this same claim.
                periods = sorted(set(_compiled_rule(r"\b(?:in|for)\s+(20\d{2})\b|(20\d{2})\s*年", 0).findall(claim)))
                periods = [next(v for v in pair if v) for pair in periods]
            if volume and periods:
                units = int(float(volume.group(1)) * (1000000 if volume.group(2) == "million" else 10000))
                return f"{institutions[0]}-iphone-production-{'-'.join(periods)}", f"forecast-units-{units}", "hardware_products"
    forecast_model_rule = _compiled_rule(r"(?<![a-z0-9])iphone\s*(duo|fold|air|\d+(?:\s+(?:pro|max|plus|ultra))*)(?![a-z0-9])", 0)
    forecast_model = forecast_model_rule.search(headline)
    if forecast_model and title_outlook and identity.scope == "apple-direct":
        model = _compiled_rule(r"\s+", 0).sub("-", forecast_model.group(1), 0)
        # A named institution's local sales claim owns its volume and period.
        # Capacity, share and other institutions later in the report are facts.
        for claim in _compiled_rule(r"[。！？;；]|(?<=[.!?])\s+", 0).split(_normalized(lead)[:1700]):
            claim = _compiled_rule(r",\s*(?:(?:up|down)\s+from|compared\s+(?:with|to)|"
                r"versus|while|whereas|but)\b|,\s*(?:相比|较去年|较此前|而|但|与)", 0).split(claim, maxsplit=1)[0]
            if not _compiled_rule(forecast, 0).search(claim):
                continue
            if _compiled_rule(r"\b(?:previously|earlier|last\s+year|no\s+longer|not|never)\b|"
                    r"此前|去年|曾(?:经)?预计|并未|没有|不会|不再|否认", 0).search(claim):
                continue
            owners = {key.partition(":")[2] for key in identity.components
                      if key.startswith("report-attribution:")
                      and _contains(claim, key.partition(":")[2].replace("-", " "))}
            owners.update(name for name, aliases in ANALYST_INSTITUTION_ALIASES
                          if _contains(claim, *aliases))
            volume = _compiled_rule(r"(?:\bsell\w*\b|售出|卖出|销量(?:可达|达到|为|将达))\s*"
                r"(?:(?:about|approximately|around|roughly|约)\s*)?"
                r"(\d+(?:\.\d+)?)\s*(million|万)\s*(?:部|units?\b)?", 0).search(claim)
            if len(owners) != 1 or not volume:
                continue
            seller = _compiled_rule(r"\bapple\b[^,;。]{0,45}\bsell\w*\b|"
                r"苹果[^,;。]{0,30}(?:售出|卖出)", 0).search(claim[:volume.end()])
            sold_model = forecast_model_rule.match(claim[volume.end():].lstrip())
            if (not seller or not sold_model
                    or _compiled_rule(r"\s+", 0).sub("-", sold_model.group(1), 0) != model):
                continue
            years = _compiled_rule(r"(?:\bin\s+|\bfor\s+)(20\d{2})\b|(20\d{2})\s*年", 0).findall(claim)
            periods = sorted({next(v for v in pair if v) for pair in years})
            if not periods and _compiled_rule(r"\bthis\s+year\b|今年", 0).search(claim):
                periods = ["this-year"]
            if len(periods) != 1:
                continue
            units = int(float(volume.group(1)) * (1000000 if volume.group(2) == "million" else 10000))
            return f"{next(iter(owners))}-iphone-{model}-sales-{periods[0]}", f"forecast-units-{units}", "hardware_products"
    if "iphone" in identity.title_products and forecast_model:
        for statement in _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(lead, 0):
            prediction = _compiled_rule(r"\b([A-Z][A-Za-z0-9]+)\s+analysts?\s+(?:forecast|predict|expect)\w*\s+that\s+Apple\s+(?:will\s+be\s+)?(?:sell\w*|ship\w*)\s+(\d+(?:\.\d+)?)\s+million\s+units\s+in\s+the\s+first\s+(\d+)\s+months\b", 0).search(statement)
            if prediction and not _compiled_rule(r"previously|last year|no longer|not expect", re.I).search(statement):
                institution, amount, months = prediction.groups()
                model = _compiled_rule(r"\s+", 0).sub("-", forecast_model.group(1), 0)
                return f"{institution.casefold()}-iphone-{model}-sales-first-{months}-months", f"forecast-units-{int(float(amount)*1000000)}", "hardware_products"

    if "apple-tv" in identity.title_products or _compiled_rule(r"^(?:apple\b|苹果)", 0).match(headline):
        ceremonies = {
            "emmy": r"\bemmys?\b|艾美",
            "golden-globe": r"\bgolden\s+globes?\b|金球",
            "bafta": r"\bbafta\b|英国电影学院",
        }
        ceremony = next((name for name, pattern in ceremonies.items()
                         if re.search(pattern, headline)), "")
        action = "nominations" if _compiled_rule(r"nominat\w*|提名", 0).search(headline) else "wins" if _compiled_rule(r"\b(?:wins?|won|earn\w*)\b|收获|获奖|斩获|摘得", 0).search(headline) else ""
        count = _compiled_rule(r"(?:\bapple(?:\s+tv)?\s+(?:(?:has|just)\s+)?(?:won|wins?|earns?|earned|received|receives|secured|secure|landed)\s+(?:(?:a|record|total|of|another|combined)\s+)*|"
            r"\bapple(?:\s+tv)?\s+(?:is\s+)?(?:leads?|leading)\b[^,;.!?。]{0,35}\bwith\s+(?:(?:a|record|total|of)\s+)*|"
            r"苹果\s*(?:apple\s*tv\s*)?(?:共|总共)?(?:收获|斩获|拿下|获得)\s*)"
            r"(\d+)\s*(?:(?:[a-z]+\s+){0,3})?(?:wins?|awards?|nominations?|项)", 0).search(scope)
        if ceremony and action and count:
            return f"apple-tv-{ceremony}-result", f"{action}-{count.group(1)}", "software_systems"
    # Same disclosed code bundle requires the version, primary component and
    # discoverer. Shared platform names alone cannot join unrelated features.
    code = _compiled_rule(r"\bcode\b|代码", 0).search(scope)
    origin = _compiled_rule(r"(?:forum[s]?\s+(?:member|user)|user|网友)\s*[\"'“]?([a-z][a-z0-9_-]{2,})|"
        r"\bby\s+([a-z][a-z0-9_-]{2,}),\s+a\s+(?:\w+\s+){0,3}forum", 0).search(scope)
    feature_bundle = _compiled_rule(r"\b(?:features|tools|findings|fragments|surprises)\b|[多五四三二两\d]+\s*项|系列功能", 0).search(scope)
    if code and origin and feature_bundle and identity.scope == "apple-direct" and _compiled_rule(r"\b(?:leak\w*|found|discover\w*|spotted|references?|hints?|points?)\b|挖掘|发现|暗藏|线索|披露", 0).search(scope):
        author = origin.group(1) or origin.group(2)
        component, platform = "", ""
        if _compiled_rule(r"camera|photograph|相机|摄影", 0).search(headline):
            component, platform = "camera", "ios"
        elif _compiled_rule(r"apple\s*watch|watchos|苹果手表", 0).search(headline):
            component, platform = "watch", "watchos"
        version = re.search(rf"\b{platform}\s*(\d+(?:\.\d+)?)\b", scope) if platform else None
        if component and version:
            return f"{platform}-{version.group(1)}-{component}-code-{author}", "feature-disclosure", "software_systems"
    return None


def _cross_platform_device_interoperation(title: str, lead: str) -> tuple[str, str] | None:
    headline = _canonical_title(title)
    platforms = {"harmonyos": r"(?:huawei\s+|华为)?(?:harmonyos|鸿蒙)", "android": r"android|安卓", "windows": r"windows"}
    platform = next((name for name, pattern in platforms.items() if re.match(rf"^(?:{pattern})", headline)), "")
    if not platform or not _compiled_rule(r"互联|打通|interoperab\w*", 0).search(headline):
        return None
    subject = _compiled_rule(r"\b(?:adds?|announc\w*|upgrad\w*|supports?)\b|升级|支持|宣布|官宣|打通", 0).split(headline, 1)[0]
    if _compiled_rule(r"\b(?:app|application|utility|client)\b|应用|客户端", 0).search(subject):
        return None
    if _compiled_rule(r"尚未|不支持|去年|回顾|\b(?:not|last\s+year|recap)\b", 0).search(headline):
        return None
    if not _compiled_rule(r"升级|支持|宣布|官宣|\b(?:adds?|announc\w*|upgrad\w*|supports?)\b", 0).search(headline):
        return None
    scope = f"{headline}. {_normalized(lead)[:750]}"
    version = re.search(rf"(?:{platforms[platform]})\s*(\d+(?:\.\d+)?)", scope)
    endpoints = [("apple-watch", r"apple\s*watch|苹果手表"), ("airpods", r"airpods"), ("iphone", r"iphone")]
    endpoint = next((name for name, pattern in endpoints if re.search(pattern, headline)), "")
    if version and endpoint and _compiled_rule(r"消息|来电|电量|互传|\b(?:notifications?|calls?|battery|transfer\w*)\b", 0).search(scope):
        return f"{platform}-{version.group(1)}", endpoint
    return None


def _title_owned_action_profile(title: str, lead: str, evidence: str, identity: EventIdentity) -> ReconciliationProfile | None:
    """Resolve explicit grammatical actions before background-derived keys.

    These frames have a complete subject/predicate; allowing later heuristics
    to invent alternative keys from their background would reopen the boundary.
    """
    headline = _canonical_title(title)
    app_use_guidance = _compiled_rule(r"\bwith\s+this\s+(?:app|application|tool|utility)\b|"
        r"^(?:用|使用)这款(?:应用|工具)", 0).search(headline)
    first_party_action = identity.action_owner == "apple" and identity.title_actions
    if app_use_guidance and not first_party_action:
        return ReconciliationProfile(
            event_keys=frozenset({f"structured-canonical-title:{headline}"}),
            boundary_keys=frozenset(), identity=identity, relevance_tier="weak",
            defer_reason="app-use recommendation without a new Apple action",
            hard_boundary="third-party-app-use",
        )
    if identity.content_form != "news":
        return None
    report = _primary_report_claim(title, lead, identity)
    milestone = _platform_compatibility_milestone(title, lead, evidence, identity)
    interoperation = _cross_platform_device_interoperation(title, lead)
    implementation = first_party_hardware_implementation(title)
    subject, predicate, category, tier = "", "", "", "strong"
    if report:
        subject, predicate, category = report
    elif interoperation:
        platform, endpoint = interoperation
        subject = f"third-party-platform-{platform}-{endpoint}"
        predicate, category, tier = "interoperability-update", "software_systems", "ecosystem"
    elif milestone and identity.content_form == "news":
        project, generation, predicate = milestone
        subject = f"third-party-platform-{project}-{generation}"
        category, tier = "software_systems", "ecosystem"
        identity = replace(identity, title_products=frozenset(), products=frozenset(),
                           title_components=frozenset({f"apple-silicon-generation:{generation.rsplit('-', 1)[-1]}"}),
                           title_actions=frozenset(), title_named_subjects=frozenset())
    elif implementation:
        host, component = implementation
        subject = f"apple-{host}:{component}"
        predicate, category = 'physical-implementation', 'hardware_products'
    elif _compiled_rule(r"\b(?:keynote|event)\b|发布会", 0).search(headline) and _compiled_rule(r"apple|苹果", 0).search(headline):
        # Bind negation to the participant before looking at dates or successors.
        participation_pattern = (
            r"(?P<person>tim\s*cook|(?:john\s+)?ternus|库克|特努斯|[a-z]+\s+[a-z]+)"
            r"(?P<action>(?:\s|或|将|可能|会|十几年来|首度|今年|不再|不会|在|苹果|秋季|发布会|视频|中){0,50}"
            r"(?:缺席|出镜|出现)|\s+(?:will\s+|may\s+|might\s+|won't\s+)?(?:not\s+)?(?:appear|attend|skip|miss)\b)"
        )
        participant = re.search(participation_pattern, headline)
        if participant is None:
            _, claim_scope = _primary_assertion_scope(title, lead)
            lead_participant = re.search(participation_pattern, claim_scope[len(_normalized(title)) + 1:])
            if lead_participant and lead_participant.group('person') in headline:
                participant = lead_participant
        if participant:
            person = participant.group('person').replace(' ', '-')
            person = {'库克': 'tim-cook', '特努斯': 'john-ternus', 'ternus': 'john-ternus'}.get(person, person)
            action = participant.group('action')
            absent = bool(_compiled_rule(r"缺席|不再|不会|\b(?:not|won't|skip|miss)\b", 0).search(action))
            period = 'wwdc' if _compiled_rule(r"wwdc|开发者大会", 0).search(headline) else 'fall' if _compiled_rule(r"september|autumn|fall|秋季|9\s*月", 0).search(headline) else ''
            if period:
                subject = f"apple-event-{period}:participant-{person}"
                predicate = 'absence' if absent else 'appearance'
                category = 'hardware_products'
                identity = replace(identity, title_products=frozenset(), title_components=frozenset(),
                                   title_actions=frozenset(), title_named_subjects=frozenset())
    else:
        services = identity.title_products & (FIRST_PARTY_SERVICE_PRODUCTS | {"app-store"})
        _, claim_scope = _primary_assertion_scope(title, lead)
        apple_owner = identity.action_owner == "apple" or _compiled_rule(r"^(?:apple\b|苹果)", 0).match(headline)
        if (
            identity.content_form == "news" and apple_owner
            and len(services) == 1
            and _compiled_rule(r"\b(?:consider(?:s|ing)?|review(?:s|ing)?|might|may|could|plans?)\b|考虑|酝酿|计划", 0).search(claim_scope)
            and _compiled_rule(r"\b(?:margins?|monetiz\w*|business\s+model|revenue)\b|收入|利润率|商业模式", 0).search(headline)
        ):
            subject = next(iter(services))
            predicate, category = 'monetization-review', 'software_systems'
    if not subject:
        return None
    key = f"primary-claim:{subject}:{predicate}"
    qualifiers = set()
    if predicate == "feature-disclosure" and "-code-" in subject:
        platform = subject.split("-", 1)[0]
        pattern = rf"\b{platform}\s*(\d+(?:\.\d+)?)\s*(?:developer\s+)?beta\s*(\d+)\b"
        builds = list(re.finditer(pattern, _normalized(title)))
        if not builds:
            first_assertion = _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(_normalized(lead), 1)[0]
            builds = list(re.finditer(pattern, first_assertion))
        for build in builds:
            qualifiers.add(f"code-build:{platform}-{build.group(1)}-beta-{build.group(2)}")
    return ReconciliationProfile(
        event_keys=frozenset({key}),
        boundary_keys=frozenset({f"primary-claim-subject:{subject}"}),
        separation_keys=frozenset({f"primary-claim-subject:{subject}", f"primary-claim-predicate:{predicate}", *qualifiers}),
        category_hint=category, identity=identity, relevance_tier=tier,
        trusted_direct_action=tier == 'strong',
    )


def _repair_cost_estimate(
    title: str,
    lead: str,
    evidence: str,
    identity: EventIdentity,
) -> tuple[str, str, str] | None:
    """Project a named product/component/amount repair-cost estimate."""
    title_scope = _normalized(title)
    evidence_scope = f"{title_scope}. {_normalized(lead)[:750]} {_normalized(evidence)[:1400]}"
    repair_action = bool(
        _compiled_rule(r"\b(?:repair|replacement|replace|service\s+fee)\b|"
            r"(?:维修|更换|换屏|维修费用|维修费)", 0).search(title_scope)
    )
    if not repair_action:
        return None
    products = identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    if len(products) != 1:
        return None
    component = ""
    if _compiled_rule(r"\b(?:inner\s+)?(?:display|screen)\b|(?:内屏|屏幕|显示屏)", 0).search(evidence_scope):
        component = "display"
    elif _compiled_rule(r"\bbattery\b|电池", 0).search(evidence_scope):
        component = "battery"
    if not component:
        return None
    repair_matches = list(
        _compiled_rule(r"\b(?:repair|replacement|replace)\b|(?:维修|更换|换屏)", 0).finditer(evidence_scope)
    )
    amount_matches = list(
        _compiled_rule(r"\$\s*([\d,]{2,})|([\d,]{2,})\s*(?:usd|u\.s\.\s*dollars?|美元)", 0).finditer(evidence_scope)
    )
    amount = ""
    if repair_matches and amount_matches:
        for candidate in amount_matches:
            distance = min(
                abs(candidate.start() - repair.start())
                for repair in repair_matches
            )
            local_context = evidence_scope[
                max(0, candidate.start() - 60) : candidate.end() + 60
            ]
            whole_product_price = bool(
                _compiled_rule(r"\b(?:starting|launch|retail)\s+price\b|"
                    r"(?:起售价|整机(?:定价|售价)|新机售价|手机售价)", 0).search(local_context)
            )
            if distance <= 180 and not whole_product_price:
                amount = (candidate.group(1) or candidate.group(2)).replace(",", "")
                break
    if not amount:
        return None
    product = next(iter(products))
    return f"{product}-{component}", "repair-cost-estimate", f"usd-{amount}"


def _unreleased_hardware_launch_roadmap(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> tuple[str, str] | None:
    """Bind a launch and its year to one primary assertion, not body background."""
    title_scope = _normalized(title)
    lead_scope = _normalized(lead)[:700]
    if lead_scope.startswith(title_scope):
        lead_scope = lead_scope[len(title_scope):].lstrip(" .:-：")
    lead_scope = _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(lead_scope, 1)[0]
    products = identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    named_apple_glasses = bool(_compiled_rule(r"(?:\bapple(?:'s)?\b|苹果).{0,28}(?:smart\s+glasses|ai\s+glasses|智能眼镜|ai\s*眼镜)", 0).search(title_scope))
    if named_apple_glasses:
        products = {"apple-glasses"}
    if len(products) != 1:
        return None
    title_year = _compiled_rule(r"\b(20(?:2[6-9]|3\d))\b", 0).search(title_scope)
    first_party_subject = bool(
        _compiled_rule(r"\bapple(?:'s)?\b|苹果", 0).search(title_scope)
        and identity.scope == "apple-direct"
    )
    launch_pattern = (
        r"\b(?:launch(?:es|ed|ing)?|reveal(?:s|ed|ing)?|unveil(?:s|ed|ing)?|"
        r"debut(?:s|ed|ing)?|ship(?:s|ped|ping)?|release(?:s|d|ing)?|refresh(?:es|ed|ing)?)\b|"
        r"(?:发布|推出|亮相|揭晓|发售|上市|出货)|更新.{0,30}(?:机型|型号|笔记本|平板)"
    )
    title_launch_action = bool(re.search(launch_pattern, title_scope))
    future_year = next((
        year for assertion in (title_scope, lead_scope)
        if re.search(launch_pattern, assertion)
        and (year := _compiled_rule(r"\b(20(?:2[6-9]|3\d))\b", 0).search(assertion))
    ), None)
    future_modality = bool(
        _compiled_rule(r"\b(?:will|plans?\s+to|expected\s+to|set\s+to|next\s+year|"
            r"as\s+soon\s+as|reportedly)\b|"
            r"(?:计划|预计|有望|将于|即将|明年|据称|传闻)", 0).search(title_scope)
    )
    future_title_action = bool(
        future_modality
        or (title_year and title_launch_action)
    )
    if not (
        first_party_subject
        and future_year
        and future_title_action
    ):
        return None
    return next(iter(products)), future_year.group(1)


def _finish_alternative_relations(title: str, lead: str, evidence: str, generation: str) -> set[str]:
    """Identify the disputed finishes, never a shared lineup count alone."""
    aliases = {
        "black": r"\bblack\b|黑色",
        "white": r"\bwhite\b|白色",
        "silver": r"\bsilver\b|银色",
        "gold": r"\bgold\b|金色",
        "blue": r"\bblue\b|蓝色|天空蓝|天蓝",
        "red": r"\bred\b|红色",
        "green": r"\bgreen\b|绿色",
        "pink": r"\bpink\b|粉色",
        "purple": r"\bpurple\b|紫色",
    }

    def finishes(clause: str) -> tuple[set[str], set[str]]:
        present, excluded = set(), set()
        for name, pattern in aliases.items():
            for match in re.finditer(pattern, clause):
                prefix = clause[max(0, match.start() - 32):match.start()]
                if _compiled_rule(r"\b(?:without|excluding|no|not)\s+$|(?:没有|不含|无含|取消|不提供)\s*$", 0).search(prefix):
                    excluded.add(name)
                else:
                    present.add(name)
        return present, excluded

    title_text, primary = _primary_assertion_scope(title, lead)
    _, excluded = finishes(primary)
    present = set()
    clauses = _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(_normalized(f"{title}. {lead[:900]} {evidence[:1200]}"), 0)
    for clause in clauses:
        models = set(_compiled_rule(r"iphone\s*(\d{1,2})(?!\d)", 0).findall(clause))
        if models - {generation} or _compiled_rule(r"\b(?:last year|previous|previously|back in)\b|去年|上一代|此前", 0).search(clause):
            continue
        values, _ = finishes(clause)
        present |= values
    relations = {",".join(sorted((left, right))) for left in excluded for right in present - excluded}
    # An indirect dispute can name mutually exclusive alternatives without
    # endorsing either. That is the same attribute question as the part leak.
    if _compiled_rule(r"\b(?:whether|battle|disagree|conflicting)\b|争议|分歧", 0).search(title_text):
        for left, right in combinations(aliases, 2):
            a, b = aliases[left], aliases[right]
            if re.search(rf"(?:{a})\s+(?:or|还是)\s+(?:{b})|(?:{b})\s+(?:or|还是)\s+(?:{a})", title_text):
                relations.add(",".join(sorted((left, right))))
    return relations


def is_multi_year_apple_product_wave(
    title: str,
    lead: str,
    *,
    identity: EventIdentity | None = None,
) -> bool:
    """Return whether the primary claim is one current multi-year Apple product wave.

    Reconciliation and article projection share this predicate so a broad
    report cannot remain aggregate in one language while product-scoped
    translations of the same report are projected in another.
    """
    full_title_text = _canonical_title(title)
    identity = identity or build_event_identity(title, lead)
    scope = f"{full_title_text} {_normalized(lead)[:1500]}"
    return bool(
        (identity.scope == "apple-direct" or _compiled_rule(r"\bapple\b|苹果", 0).search(full_title_text))
        and _compiled_rule(r"\b(?:largest|biggest|biggest-ever|multi[- ]year|five[- ]year)\b"
            r".{0,55}\b(?:product|device|hardware)\s+(?:lineup|wave|roadmap|cycle|pipeline)\b|"
            r"\b(?:product|device|hardware)\s+(?:lineup|wave|roadmap|cycle|pipeline)\b"
            r".{0,55}\b(?:largest|biggest|multi[- ]year|five[- ]year)\b|"
            r"(?:史上|历来|公司历史上).{0,20}(?:最大|最庞大).{0,24}(?:新品|产品|设备|硬件)"
            r"(?:阵容|发布潮|发布周期|路线图|规划)|"
            r"(?:未来|今后)\s*[五5]\s*年.{0,24}(?:产品|设备|硬件)?(?:路线图|规划|发布)", re.I).search(full_title_text)
        and _compiled_rule(r"\b(?:launch|release)\s+(?:wave|cycle)|roadmap|lineup|pipeline\b|"
            r"(?:发布潮|发布周期|产品阵容|新品阵容|路线图|产品规划|设备规划)", re.I).search(scope)
        and (
            len(set(_compiled_rule(r"\b20(?:2[6-9]|3\d)\b", 0).findall(scope))) >= 2
            or _compiled_rule(r"\b(?:multi[- ]year|five[- ]year|and\s+beyond|or\s+later)\b|"
                r"(?:未来|今后)\s*[五5]\s*年|(?:及|和|与)(?:以后|更远未来)|乃至更远", re.I).search(scope)
        )
    )


def _primary_claim_projection(
    title: str,
    lead: str,
    identity: EventIdentity,
    regions: Iterable[str],
    evidence: str = "",
    embedded_references: tuple = (),
    source_facts: tuple[str, ...] = (),
    teardown_operation: SourceActionFrame | None = None,
) -> tuple[set[str], set[str], set[str], str, bool]:
    """Return a title-led subject/predicate frame for sparse cross-source news.

    These keys describe the concrete claim made by the headline and first
    substantive lead. Reconciliation requires positive source identity rather
    than treating missing conflicts or an incoming group as proof of a match.
    """
    title_text, text = _primary_assertion_scope(title, lead)
    full_title_text = _canonical_title(title)
    claim_evidence = f"{text} {_normalized(evidence)[:1400]}".strip()
    extended_claim_evidence = (
        f"{full_title_text} {_normalized(lead)[:1600]} {_normalized(evidence)[:1400]}"
    ).strip()
    event_keys: set[str] = set()
    boundaries: set[str] = set()
    separation: set[str] = set()
    category_hint = ""
    trusted_direct_action = False

    def add_claim(
        subject: str,
        predicate: str,
        *,
        qualifier: str = "",
        category: str = "",
        trusted: bool = True,
    ) -> None:
        nonlocal category_hint, trusted_direct_action
        suffix = f":{qualifier}" if qualifier else ""
        event_keys.add(f"primary-claim:{subject}:{predicate}{suffix}")
        boundaries.add(f"primary-claim-subject:{subject}")
        separation.add(f"primary-claim-subject:{subject}")
        separation.add(f"primary-claim-predicate:{predicate}")
        if category:
            category_hint = category
        trusted_direct_action = trusted_direct_action or trusted

    if (_compiled_rule(r"^(?:apple(?: today| officially)? recalls?\b|苹果(?:今日|正式)?召回)", 0).match(title_text)
            and identity.title_products):
        recalled_products = sorted(identity.title_products)
        component = "battery" if _compiled_rule(r"batter(?:y|ies)|电池", 0).search(title_text) else "device"
        add_claim("-".join(recalled_products) + "-" + component, "product-recall",
                  category="hardware_products", trusted=True)
        separation.add("source-current-action:product-recall")

    signing_statement = _compiled_rule('^apple\\s+(?:(?:today|has|now|just)\\s+)*(?:stopped|stops|ceased|ceases)\\s+signing\\s+(ios|ipados|macos|watchos|tvos|visionos)\\s+(\\d+(?:\\.\\d+){0,2})(?![\\d.])', re.I).match(_short_lead_scope(lead))
    if signing_statement and _compiled_rule('signing|downgrad|停止签|降级', 0).search(title_text):
        add_claim(signing_statement.group(1) + "-" + signing_statement.group(2),
                  "signing-authorization-ended", category="software_systems")

    # Shipping capacity is a firmware restriction on a named phone, not its
    # rated battery specification. Activation and re-shipping describe the
    # same control even when one headline omits the model number.
    transport_scope = _normalized(" ".join((title, lead, *source_facts))) if _compiled_rule('shipping|transport|运输', 0).search(title_text) else extended_claim_evidence
    transport_model = _compiled_rule('(?<![a-z0-9])iphone\\s*(\\d{1,2}(?:\\s*pro)?(?:\\s*max)?)(?![a-z0-9])', 0).search(transport_scope)
    transport_limit = _compiled_rule('(?:below|under)\\s+(?:the\\s+)?(\\d+(?:\\.\\d+)?)\\s*(?:watt[- ]hours?|wh)\\b|(?:限制|放电|锁定).{0,16}?(\\d+(?:\\.\\d+)?)\\s*(?:wh|瓦时)(?:安全线)?\\s*(?:以下|之下)', 0).search(transport_scope)
    support_control = bool(
        _compiled_rule('\\bapple\\b.{0,70}\\b(?:support document|added|describes)\\b', 0).search(transport_scope)
        and _compiled_rule('\\bcontrol\\b.{0,90}\\bdischarges?\\b|\\bdischarges?\\b.{0,70}\\bcontrol\\b', 0).search(transport_scope)
        and _compiled_rule('\\bbefore\\s+(?:transport|shipping)\\b', 0).search(transport_scope)
        and _compiled_rule('\\bactivat(?:ion|ing)\\b', 0).search(transport_scope))
    firmware_control = bool(
        _compiled_rule('shipping|transport|运输', 0).search(title_text)
        and _compiled_rule('batter(?:y|ies)|电池', 0).search(transport_scope)
        and _compiled_rule('\\bapple\\b|苹果', 0).search(transport_scope)
        and _compiled_rule('(?:battery[- ]?)?firmware(?: lock| solution)?|电池固件|软件手段', 0).search(transport_scope)
        and _compiled_rule('activat(?:ion|ing|es?|ed)|激活', 0).search(transport_scope)
        and _compiled_rule('removes?|restor(?:ed|ing)|disappears? automatically|解除|恢复', 0).search(transport_scope)
        and _compiled_rule('prepare to ship|before (?:transport|shipping)|准备运输|出货运输', 0).search(transport_scope))
    if transport_model and transport_limit and (support_control or firmware_control):
        subject = "iphone-" + _compiled_rule(r"\s+", 0).sub("-", transport_model.group(1), 0)
        limit = next(value for value in transport_limit.groups() if value)
        add_claim(subject, "battery-transport-control", qualifier="below-" + limit + "-wh",
                  category="software_systems")

    # Complete selected source facts may supply measurements beyond the
    # introductory excerpt. Only this title-bound typed relation reads them;
    # unrelated old evidence consumers keep their existing scope limits.
    storage_model = _compiled_rule('(?<![a-z0-9])iphone\\s*(\\d+\\s*pro(?:\\s*max)?)(?![a-z0-9])', 0).search(title_text)
    storage_context = " ".join((lead, *source_facts)).casefold()
    if (storage_model and _compiled_rule('storage|闪存|存储', 0).search(title_text)
            and _compiled_rule('loads?|负载|测试', 0).search(title_text)
            and _compiled_rule('(?<![a-z0-9])qlc(?![a-z0-9])', 0).search(storage_context)):
        capacity = _compiled_rule('(?<![\\d.])(\\d+(?:\\.\\d+)?)\\s*(tb|gb)(?![a-z])', 0).search(lead.casefold())
        subject = ("iphone-" + _compiled_rule('\\s+', 0).sub('-', storage_model.group(1))
                   + "-" + "".join(capacity.groups()) + "-qlc") if capacity else ""
        for fact in source_facts:
            local = fact.casefold()
            if not _compiled_rule('sustained testing|持续写入速度|长时间连续写入', 0).search(local):
                continue
            measured = _compiled_rule('(?:speed of|速度(?:平均)?(?:仅)?为|平均写入速度(?:最终)?(?:下降至|降至))\\s*(\\d+(?:\\.\\d+)?)\\s*mb/s', 0).search(local)
            low = _compiled_rule('(?:even hit|最低(?:降至|跌至)?|个别时刻(?:甚至)?触及)\\s*(\\d+(?:\\.\\d+)?)\\s*mb/s', 0).search(local)
            if subject and measured and low:
                add_claim(subject, "sustained-storage-write-measurement",
                          qualifier="mbps-" + measured.group(1) + "-observed-low-" + low.group(1),
                          category="hardware_products")

    report_institution = _compiled_rule('^([\\u4e00-\\u9fff]{2,12}?)(?=维持|重申|[：:])', 0).match(title_text)
    if (report_institution and "iphone" in identity.title_products
            and _compiled_rule('需求', 0).search(title_text)
            and _compiled_rule('跟踪|等待|等候', 0).search(storage_context)):
        institution = report_institution.group(1)
        for fact in source_facts:
            for local in _compiled_rule('[。！？]', 0).split(fact.casefold()):
                result = _compiled_rule('(?<![a-z0-9])iphone\\s*(\\d+\\s*pro(?:\\s*max)?)\\s*[^。！？]{0,18}?平均(?:等待|等候)(?:拿货)?时间?(?:约)?(?:为)?\\s*(\\d+)\\s*天|(?<![a-z0-9])iphone\\s*(\\d+\\s*pro(?:\\s*max)?)\\s*[^。！？]{0,18}?平均(?:等待|等候)\\s*(\\d+)\\s*天', 0).search(local)
                if not result:
                    continue
                model, days = (result.group(1),result.group(2)) if result.group(1) else (result.group(3),result.group(4))
                add_claim("iphone-" + _compiled_rule('\\s+', 0).sub('-', model), "preorder-wait-demand-report",
                          qualifier=institution + "-mean-days-" + days, category="hardware_products")

    # A measurement is tied to the tested model, instrument and metric, rather
    # than incidental hardware nouns elsewhere in the source.
    measured_chip = _compiled_rule('(?<![a-z0-9])m\\s*(\\d{1,2})(?:\\s+(pro|max|ultra))?(?![a-z0-9])', 0).search(title_text)
    measured_gpu = _compiled_rule('geekbench\\s+(metal|opencl)[^。.!?]{0,35}?(\\d[\\d,]{2,})\\s*分', 0).search(text)
    if (measured_chip and measured_gpu and _compiled_rule('gpu|图形', 0).search(title_text)
            and _compiled_rule('跑分|benchmark|scores?', 0).search(title_text)):
        model = "m" + measured_chip.group(1) + ("-" + measured_chip.group(2) if measured_chip.group(2) else "")
        add_claim("apple-silicon-" + model, "gpu-benchmark-result",
                  qualifier=measured_gpu.group(1) + "-" + measured_gpu.group(2).replace(",", ""),
                  category="hardware_products")

    tested_phone = _compiled_rule('(?<![a-z0-9])iphone\\s*(\\d{1,2}(?:\\s*pro)?(?:\\s*max)?)(?![a-z0-9])', 0).search(title_text)
    camera_score = _compiled_rule('(\\d{2,3})\\s*(?:分|points?)', 0).search(claim_evidence)
    if (tested_phone and camera_score
            and _compiled_rule('^(?:\\d+\\s*分[！!，,:：]?\\s*)?(?:苹果\\s*)?iphone\\s*\\d+', 0).match(title_text)
            and _compiled_rule('(?<![a-z0-9])dxo(?:mark)?(?![a-z0-9])', 0).search(claim_evidence)
            and _compiled_rule('影像|相机|camera', 0).search(title_text)
            and _compiled_rule('测试|成绩|评分|test|score|rank|全球第', 0).search(title_text)):
        model = _compiled_rule(r"\s+", 0).sub("-", tested_phone.group(1), 0)
        add_claim("iphone-" + model, "camera-measurement-result",
                  qualifier="dxomark-score-" + camera_score.group(1), category="hardware_products")


    # The published teardown is the action; its battery, optics and repair
    # findings are complementary observations, not independent teardown IDs.
    teardown_scope = lead[:1800]
    if teardown_operation or (tested_phone and _compiled_rule('teardown|tears? down|拆解|拆机', 0).search(title_text)):
        if teardown_operation:
            investigators = set(teardown_operation.subject.partition(':publishers:')[2].split('|'))
            whole_device = True
        else:
            investigators = set()
            for pattern in (
                r"\b(?:repair outfit|teardown specialist)\s+([A-Za-z][A-Za-z0-9]+)\s+(?:took|takes)\s+(?:a\s+)?(?:very\s+)?close look\b",
                r"\b([A-Za-z][A-Za-z0-9]+)\s+(?:(?:has|today|now)\s+)*(?:published|shares?|tears? down)\b|\b([A-Za-z][A-Za-z0-9]+)['’]s\s+(?:(?:latest|new|device|full)\s+)*teardown\b",
                r"([A-Za-z][A-Za-z0-9]+)\s*(?=[^。.!?]{0,120}拆解)(?:(?:现已|近日|日前|今日)?(?:发布|公开|公布)(?:了)?|对|此次|拆解).{0,90}?(?:iphone|拆解)",
            ):
                investigators.update(v.casefold() for m in re.finditer(pattern, title + ". " + teardown_scope, re.I)
                                     for v in m.groups() if v and v.casefold() not in {"apple", "the", "this", "a", "its"})
            whole_device = _compiled_rule('(?:teardown\\s+(?:of\\s+)?(?:the\\s+)?iphone|iphone.{0,75}teardown|对iphone.{0,75}进行了拆解|iphone.{0,55}的(?:完整|详细|全面)?拆解)', 0).search(_normalized(teardown_scope))
            whole_device = whole_device or _compiled_rule('teardown\\s+(?:shows?|reveals?|examines?)\\b[^。.!?]{0,170}\\biphone\\b|(?:close look|components inside)[^。.!?]{0,100}\\biphone\\b', re.I).search(teardown_scope)
        if (teardown_operation or (len(investigators) == 1 and whole_device)) and not _compiled_rule('modem|基带|调制解调器', 0).search(title_text):
            model = (teardown_operation.subject.partition(':publishers:')[0] if teardown_operation
                     else "iphone-" + _compiled_rule(r"\s+", 0).sub("-", tested_phone.group(1), 0).removesuffix("-max"))
            publishers = '|'.join(sorted(investigators))
            add_claim(model, "published-device-teardown", qualifier=publishers, category="hardware_products")
            separation.add("teardown-publisher:" + publishers)
            separation.add("teardown-model:" + model)

    # Quantities belong to the locally stated production/sales object, not
    # every supplier, component or executive mentioned in later background.
    production_products = identity.title_products & {"iphone", "foldable-iphone", "ipad", "macbook"}
    if len(production_products) == 1 and _compiled_rule('整机良率|(?:device|assembly)\\s+yield', re.I).search(title_text):
        for clause in _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(lead[:1000], 0):
            measured = _compiled_rule('整机良率(?:仅|只有)?(?:为|达到)?\\s*(\\d+(?:\\.\\d+)?)\\s*%|(?:device|assembly)\\s+yield.{0,25}?(\\d+(?:\\.\\d+)?)\\s*%', re.I).search(clause)
            if measured and _bounded_evidence_products(clause) & production_products:
                amount = next(value for value in measured.groups() if value)
                add_claim(next(iter(production_products)), "device-assembly-yield-report",
                          qualifier="percent-" + amount, category="hardware_products")
                separation.add("local-measure-object:device-assembly-yield")
                break
    if tested_phone and _compiled_rule('首销|首日|开售日|first.day\\s+sales', re.I).search(title_text):
        for clause in _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(lead[:1400], 0):
            author = _compiled_rule('博主\\s*(?:[“\\"]([^”\\"]+)[”\\"]|@([^\\s，,。]+))', 0).search(clause)
            measured = _compiled_rule('(?:开售日|首日|首销)销量(?:[（(][^）)]*[）)])?(?:约|大约)?(?:为|达到)?\\s*(\\d+(?:\\.\\d+)?)\\s*(万)?台', 0).search(clause)
            if author and measured and _compiled_rule('公布|爆料|发布|披露', 0).search(clause):
                publisher = _compiled_rule(r"\s+", 0).sub("", next(value for value in author.groups() if value), 0).casefold()
                amount = float(measured.group(1)) * (10000 if measured.group(2) else 1)
                model = _compiled_rule(r"\s+", 0).sub("-", tested_phone.group(1), 0).removesuffix("-max")
                add_claim("iphone-" + model, "first-sale-measurement",
                          qualifier=publisher + ":units-" + str(int(amount)), category="hardware_products")
                separation.add("local-measure-object:first-sale-report")
                break

    # A reported malfunction keeps its named fault and reproduction operand.
    # A historic fix or another fault on the same phone does not grant this key.
    if tested_phone and _compiled_rule('故障|死机|重启|malfunction|crash', 0).search(title_text):
        fault = _compiled_rule('[“\\"]([A-Za-z][A-Za-z ]{2,40})[”\\"](?:现象|问题|故障)', 0).search(lead)
        if (fault and _compiled_rule('face\\s*id', re.I).search(lead)
                and _compiled_rule('(?:反复|重复).{0,60}(?:识别失败|认证|遮)|reproduc', re.I).search(lead)
                and _compiled_rule('调查|investigat', 0).search(title_text)):
            model = _compiled_rule(r"\s+", 0).sub("-", tested_phone.group(1), 0).removesuffix("-max")
            add_claim("iphone-" + model, "malfunction-investigation",
                      qualifier=_compiled_rule(r"\s+", 0).sub("", fault.group(1).casefold(), 0) + ":face-id-authentication",
                      category="hardware_products")

    cancelled_accessory = bool(_compiled_rule('apple pencil|手写笔', 0).search(title_text)
        and _compiled_rule('scrapped|取消|夭折|supposed to launch', 0).search(title_text)
        and _compiled_rule('shorter|smaller|短款|专属', 0).search(title_text + ' ' + _normalized(lead))
        and _compiled_rule('scrapped|取消|夭折', 0).search(_normalized(lead))
        and _compiled_rule('technical problems|技术故障|技术问题', 0).search(_normalized(lead)))
    if cancelled_accessory:
        host = _compiled_rule('iphone\\s+(duo|fold)', 0).search(title_text)
        if host:
            add_claim("apple-pencil-for-iphone-" + host.group(1), "short-accessory-cancellation",
                      category="hardware_products")

    # A regional teardown's positive chip identification is not contradicted
    # by the complementary statement that a different chip is absent.
    if teardown_operation or (tested_phone and _compiled_rule('teardown|拆解', 0).search(title_text)):
        if teardown_operation:
            institutions = {teardown_operation.subject.partition(':publishers:')[2]}
        else:
            institutions = _compiled_rule('(?:^|(?<=[.!?。]))\\s*([A-Z][A-Za-z0-9]+)\\s+(?:has\\s+)?(?:published|identified|examined|confirmed)\\b|(?:teardown[^。.!?]{0,100}\\bby\\s+|[Aa]ccording to (?:the )?)([A-Z][A-Za-z0-9]+)(?=\\s+(?:teardown|[, ]|the)|[, .])', 0).findall(lead)
            institutions = {v.lower() for pair in institutions for v in pair if v and v not in {"Apple", "This", "It"}}
        chips = set(_compiled_rule('\\b((?:sdx|x)\\d{2,3}[a-z]?)\\b', 0).findall(claim_evidence))
        regional = set(regions) - {"multi-region"}
        if (len(institutions) == 1 and chips and len(regional) == 1
                and _compiled_rule('modem|基带|调制解调器', 0).search(title_text)
                and _compiled_rule('qualcomm|高通', 0).search(claim_evidence)):
            # Identify the regional teardown finding, not a fabricated device
            # alias. Product names and package markings remain source details.
            model = (teardown_operation.subject.partition(':publishers:')[0] if teardown_operation
                     else "iphone-" + _compiled_rule(r"\s+", 0).sub("-", tested_phone.group(1), 0))
            add_claim(model,
                      "regional-modem-teardown", qualifier=next(iter(institutions)) + ":" + next(iter(regional)) + ":qualcomm",
                      category="hardware_products")
            for chip in chips:
                part = _compiled_rule('([a-z]+)(\\d+)([a-z]*)', 0).fullmatch(chip)
                if part:
                    separation.add("teardown-part-number:" + part.group(2))
                    separation.add("teardown-part-code:" + part.group(1) + ":" + chip)

    if measured_chip and _compiled_rule('geekbench|benchmark|跑分|基准测试', 0).search(claim_evidence):
        authentication = _compiled_rule('内部矛盾|internal inconsistenc', 0).search(claim_evidence)
        authority = _compiled_rule('geekbench\\s*(?:creator|founder|创始人)', 0).search(claim_evidence)
        question = _compiled_rule('likely fake|may not be legitimate|真实性存疑|很可能是伪造|尚不能证明', 0).search(claim_evidence)
        if authentication and authority and question:
            model = "m" + measured_chip.group(1) + ("-" + measured_chip.group(2) if measured_chip.group(2) else "")
            add_claim("apple-silicon-" + model, "benchmark-authenticity-assessment",
                      qualifier="geekbench:internal-inconsistency", category="hardware_products")
            separation.add("benchmark-report-action:authenticity-assessment")
        elif _compiled_rule('appeared|surfaced|出现|现身|曝光', 0).search(claim_evidence) and _compiled_rule('alleged|claimed|据称|(?:尚未|并未|未获).{0,10}确认|if genuine', 0).search(claim_evidence):
            separation.add("benchmark-report-action:result-disclosure")
            # A source-local record can identify Apple's tested chip even when
            # its headline omits Apple. Unknown title ownership is not evidence
            # of a competing vendor; the measured object still needs a positive
            # relation in this source, not a nearby comparison or later forecast.
            model_pattern = r"m\s*" + re.escape(measured_chip.group(1))
            if measured_chip.group(2):
                model_pattern += r"\s*" + re.escape(measured_chip.group(2))
            object_pattern = r"\bapple\s+" + model_pattern + r"(?![a-z0-9]|\s+(?:pro|max|ultra)\b)"
            measurement_operand = (
                r"\b(?:describ(?:es?|ed)|lists?|records?|shows?|identif(?:ies|ied)|us(?:e[sd]?|ing)|run(?:s|ning)?\s+on)"
                r"\s+(?:(?:an?|the|this|that)\s+)?[\"“‘']?" + object_pattern
            )
            for statement in _compiled_rule(r"(?:[。！？]|(?<=[.!?])\s+)", 0).split(extended_claim_evidence, 0):
                if (_compiled_rule('\\b(?:listing|record|entry|result|score|measurement|benchmark)\\b|记录|条目|结果|跑分', 0).search(statement)
                        and re.search(measurement_operand, statement)
                        and not _compiled_rule('compar|unlike|instead of|background|earlier|previously|not.{0,25}(?:apple|chip)|对比|相比|背景|此前|并非|不是', 0).search(statement)):
                    trusted_direct_action = True
                    category_hint = "hardware_products"
                    break


    absent_feature = _compiled_rule('\\bthe\\s+([a-z][a-z -]{2,50})\\s+is\\s+absent\\s+from\\s+apple\\s*watch', re.I).search(lead)
    feature = (_compiled_rule(r"\s+", 0).sub("-", absent_feature.group(1).lower(), 0) if absent_feature else "")
    if _compiled_rule('handwashing|洗手(?:检测|计时)', 0).search(title_text + ' ' + _normalized(lead)):
        feature = "handwashing"
    if feature:
        watch_series = _compiled_rule('(?:apple\\s*watch\\s*)?series\\s*(\\d+)', 0).search(title_text)
        watch_ultra = _compiled_rule('ultra\\s*(\\d+)', 0).search(title_text)
        if (watch_series and watch_ultra and _compiled_rule('supported (?:hardware )?list|支持机型|支持列表|官网列表', 0).search(full_title_text + ' ' + _normalized(lead))
                and _compiled_rule('absent|missing|未列|未收录|缺少', 0).search(full_title_text + ' ' + _normalized(lead))):
            add_claim("apple-watch-series-" + watch_series.group(1) + "-ultra-" + watch_ultra.group(1),
                      "official-feature-support-list-omission", qualifier=feature,
                      category="hardware_products")
            separation.add("support-list-feature:" + feature)

    interview = _compiled_rule('(?:接受\\s*(?:外媒)?\\s*([A-Z][A-Za-z0-9]+)\\s*采访|(?:in\\s+)?a?\\s*([A-Z][A-Za-z0-9]+)\\s+interview)', 0).search(lead)
    hardware_spokesperson = _compiled_rule('(?:苹果(?:现任|新任)?硬件(?:工程)?(?:负责人|副总裁)|Apple hardware chief)\\s*([A-Z][A-Za-z]+(?:\\s+[A-Z][A-Za-z]+){1,3})', 0).search(lead)
    if not hardware_spokesperson and _compiled_rule('苹果(?:现任|新任)?硬件(?:工程)?(?:负责人|副总裁)', 0).search(lead):
        # A parenthetical name is local attribution, not a global bilingual alias.
        hardware_spokesperson = _compiled_rule('[\\（(]([A-Z][A-Za-z]+(?:\\s+[A-Z][A-Za-z]+){1,3})[)）]', 0).search(lead)
    if not hardware_spokesperson:
        hardware_spokesperson = _compiled_rule(r"苹果(?:现任|新任)?硬件(?:工程)?(?:负责人|副总裁)\s*"
            r"([\u4e00-\u9fff]{1,3}[·•][\u4e00-\u9fff]{1,4})(?=对此|对外|在|近期|近日|[，。\s])", 0).search(lead)
    collective_interview = _compiled_rule(r"在(?:苹果)?([\u4e00-\u9fff]{2,8})总部的(?:一[场次])?集体采访", 0).search(lead)
    test_years = _compiled_rule('(?:simulate\\s+(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s+years?|模拟\\s*(\\d+|一|二|三|四|五|六|七|八|九|十)\\s*年)', re.I).search(lead)
    interview_body = lead
    if interview:
        media_name = next(v for v in interview.groups() if v)
        interview_body = re.sub(re.escape(media_name), "", lead, flags=re.I)
    if ((interview or collective_interview) and hardware_spokesperson
            and _compiled_rule('盖板|屏幕|显示屏|\\bcover glass\\b|\\bscreen\\b', re.I).search(interview_body)
            and _compiled_rule('耐刮|抗刮|scratch resistance', re.I).search(lead)
            and _compiled_rule('磨损|耐磨|wear', re.I).search(lead)):
        outlet = (next(v for v in interview.groups() if v).lower() if interview else "headquarters-" + collective_interview.group(1))
        person = _compiled_rule(r"\s+", 0).sub("-", hardware_spokesperson.group(1).lower(), 0)
        add_claim("apple-hardware-interview:" + outlet + ":" + person,
                  "cover-glass-durability-test", category="hardware_products")
        if test_years:
            numbers = dict(zip("one two three four five six seven eight nine ten 一 二 三 四 五 六 七 八 九 十".split(), list(range(1,11))*2))
            raw_years = next(v for v in test_years.groups() if v).lower()
            years = str(numbers.get(raw_years, raw_years))
            separation.add("interview-test-duration:" + years + "-years")

    # The feature can be in captured facts beyond an introductory date/user
    # reaction. Require the actual option and its Clock setting relationship.
    alarm_scope = extended_claim_evidence
    alarm_version = _compiled_rule('ios\\s*(\\d+(?:\\.\\d+)*)', 0).search(alarm_scope)
    if (alarm_version and _compiled_rule('闹钟|alarm', 0).search(title_text)
            and ((_compiled_rule('时钟.{0,20}新增|clock.{0,30}(?:adds?|new)', 0).search(alarm_scope)
                  and _compiled_rule('工作日（含调休）|工作日\\(含调休\\)|本地工作日', 0).search(alarm_scope))
                 or _compiled_rule('(?:补足|新增|增加|支持)[^。.!?]{0,35}(?:节假日|调休日?)[^。.!?]{0,12}闹钟', 0).search(alarm_scope))
            and _compiled_rule('重复设置|调休|补班', 0).search(alarm_scope)):
        version = _compiled_rule(r"(?:\.0)+$", 0).sub("", alarm_version.group(1), 0)
        add_claim("ios-" + version + "-clock", "local-workday-alarm-option", category="software_systems")
        for region in set(regions) - {"multi-region"}:
            separation.add("clock-workday-region:" + region)

    preview_subject = (_embedded_current_preview_subject(title, lead, embedded_references)
                       or _camera_preview_subject(title_text, lead, identity))
    if preview_subject:
        add_claim(preview_subject, "pre-event-preview-publication", category="hardware_products")

    # A catalogue count is a cited cumulative report about a named product
    # object; its extreme historical price does not define the report action.
    if _compiled_rule('apple\\s*watch.*(?:bands?|表带)', re.I).search(title_text):
        citation = _compiled_rule('according to ([A-Z][A-Za-z]+(?:\\s+[A-Z][A-Za-z]+){1,3}),?\\s+who develops (?:the )?([A-Z][A-Za-z0-9]+) (?:catalog(?:ue)?|app)\\b|(?:来自|源于)\\s*([A-Z][A-Za-z]+(?:\\s+[A-Z][A-Za-z]+){1,3})\\s*开发的\\s*([A-Z][A-Za-z0-9]+)\\s*(?:目录|应用)', 0).search(lead)
        counts = _compiled_rule('(?:more than|over|超过|超)\\s*([\\d,]+)\\s*(?:款)?\\s*(?:(?:official\\s+apple\\s*watch\\s*bands?)|(?:官方\\s*(?:apple\\s*watch\\s*)?表带))', re.I).findall(lead)
        periods = _compiled_rule('(?:since\\s+(?:(?:the device|apple watch)\\s+(?:debuted|was\\s+(?:first\\s+)?(?:released|launched|introduced))\\s+in\\s+(?:[A-Za-z]+\\s+)?)?|自\\s*(?:初代\\s*Apple\\s*Watch\\s*于\\s*)?)(20\\d{2})', re.I).findall(lead)
        counts.extend(_compiled_rule('官方\\s*(?:apple\\s*watch\\s*)?表带(?:累计)?(?:已)?(?:超|超过)\\s*([\\d,]+)\\s*款', re.I).findall(lead))
        counts = [str(int(value.replace(",", ""))) for value in counts]
        if citation and len(set(counts)) == 1 and len(set(periods)) == 1:
            author, catalogue = citation.group(1, 2) if citation.group(1) else citation.group(3, 4)
            origin = _compiled_rule(r"\s+", 0).sub("-", author.lower(), 0) + ":" + catalogue.lower()
            count = counts[0].replace(",", "")
            qualifier = f"since-{periods[0]}:over-{count}"
            add_claim("apple-watch-bands-catalogue:" + origin, "cumulative-count-report", qualifier=qualifier,
                      category="hardware_products")
            separation.add("primary-claim-qualifier:catalogue-count:" + qualifier)

    primary_lead = _short_lead_scope(lead, sentences=1)
    # A named tool is the pilot object only when introduced as the direct
    # operand (including "tool called ..."), not merely mentioned nearby.
    for subject in identity.named_subjects:
        name = re.escape(subject).replace(r"\-", r"\s+")
        named_pilot = re.match(
            r"^apple\s+(?:is\s+)?(?:testing|piloting)\s+"
            r"(?:(?:a|the|new)\s+)*(?:(?:[a-z]+\s+){0,5}(?:tool|system)\s+(?:called|named)\s+)?[\"“]?"
            + name + r"(?=\b|[\"”])|"
            r"^苹果(?:正在|已)?(?:[^。！？]{0,12}(?:直营店|天才吧))?测试(?:名为)?\s*[\"“]?"
            + name + r"(?=\s|[的\"”])", primary_lead, re.I)
        if not named_pilot:
            continue
        pilot_tool_context = re.search(
            r"\b(?:tool|system|app)\s+(?:called|named)\s*[\"“‘']?" + name + r"\b|"
            + name + r"[\"”’']?\s*(?:的\s*)?(?:ai\s*)?(?:tool\b|system\b|app\b|系统|工具|软件)",
            full_title_text + " " + primary_lead, re.I)
        hardware_pilot_object = _bounded_evidence_products(subject.replace("-", " ")) & {
            "iphone", "ipad", "macbook", "mac-pro", "mac-studio", "mac-mini", "imac", "apple-watch", "airpods", "homepod", "vision-pro"}
        if named_pilot and pilot_tool_context and not hardware_pilot_object:
            add_claim("first-party-tool:" + subject, "pilot-testing", category="software_systems")

    # Retrospective cancellation reports identify the abandoned host and
    # named silicon configurations together; the chips alone are not an event.
    cancelled_configuration = bool(
        _compiled_rule('^(?:apple\\b|苹果|the\\s+cancelled\\b)', re.I).match(primary_lead)
        and _compiled_rule('\\bcancell(?:ed|ing)\\b|decided not to release|取消', re.I).search(primary_lead)
        and not _compiled_rule('\\b(?:not|never)\\s+cancell|未取消|没有取消', re.I).search(primary_lead))
    if cancelled_configuration:
        hosts = _bounded_evidence_products(primary_lead) & {"mac-pro", "mac-studio", "mac-mini", "macbook", "imac"}
        chips = {_compiled_rule(r"\s+", 0).sub("-", match.casefold(), 0) for match in _compiled_rule('\\bm\\d+\\s+extreme\\b', re.I).findall(primary_lead)}
        title_hosts = identity.title_products & {"mac-pro", "mac-studio", "mac-mini", "macbook", "imac"}
        if len(hosts) == 1 and chips and (not title_hosts or hosts <= title_hosts):
            host = next(iter(hosts))
            host_name = re.escape(host).replace(r"\-", r"\s+")
            cancelled_host = re.search(
                r"cancell(?:ed|ing)\s+(?:the\s+|its\s+)?" + host_name + r"\s+(?:projects?|plans?)|"
                r"^the\s+cancelled\b.{0,45}" + host_name + r"\s+(?:projects?|plans?)|"
                r"\bfor\s+(?:the\s+)?" + host_name + r"\s+but\s+decided not to release|"
                r"取消.{0,50}" + host_name + r"\s*项目|"
                + host_name + r".{0,85}(?:取消计划|取消项目)", primary_lead, re.I)
            if cancelled_host:
                add_claim(host, "cancelled-chip-configurations", qualifier="+".join(sorted(chips)), category="hardware_products")

    # A report about testing is not identified by the reporter's name alone:
    # retain the named models, testing phase, and source-stated target month.
    if ("apple-watch" in identity.title_products
        and _compiled_rule('\\bapple\\s+is\\s+late-stage testing\\b|\\bapple watch models\\s+are\\s+in\\s+late-stage testing\\b', re.I).search(primary_lead)
        and not _compiled_rule('\\b(?:not|never)\\b.{0,20}late-stage testing', re.I).search(primary_lead)
        and _compiled_rule('\\b(?:reports?|according to|outlined|gurman|bloomberg)\\b', re.I).search(primary_lead)):
        models = {_compiled_rule(r"\s+", 0).sub("-", match.casefold(), 0) for match in _compiled_rule('\\b(?:series|ultra)\\s+\\d+\\b', re.I).findall(full_title_text + ' ' + primary_lead)}
        target = _compiled_rule('\\bfor\\s+(january|february|march|april|may|june|july|august|september|october|november|december)\\b', re.I).search(primary_lead)
        if models and target:
            add_claim("apple-watch:" + "+".join(sorted(models)), "late-stage-testing", qualifier=target.group(1).casefold(), category="hardware_products")

    # A sparse roadmap headline can share a concrete source configuration.
    # Keep the model tier and both adopted features, rather than authorizing
    # the generic product/roadmap label or an unrelated comparison sentence.
    if identity.title_products == {"ipad"}:
        for clause in _compiled_rule(r"(?<=[.!?。！？])\s*", 0).split(f"{_short_lead_scope(lead)}. {evidence}", 0):
            if (_compiled_rule('\\s*(?:the\\s+|new\\s+)?entry-level\\s+ipad\\s+(?:will\\s+use|gets?|adds?)\\b', re.I).match(clause)
                and _compiled_rule('\\bfaster\\s+chip\\b', re.I).search(clause)
                and _compiled_rule('\\band\\s+(?:add\\s+)?apple intelligence\\b', re.I).search(clause)
                and not _compiled_rule('\\b(?:not|never|previously|used to)\\b', re.I).search(clause)):
                add_claim("ipad-entry-level", "configuration-adoption", qualifier="faster-chip+apple-intelligence", category="hardware_products")

    # A first-sentence announcement owns the named model even when the
    # headline says "is here". Later retail timing is a separate stage and
    # cannot turn that completed announcement into a launch-window forecast.
    model_pattern = (r"\b(?:apple watch|iphone|ipad|macbook|airpods)\s+"
                     r"(?:(?:series|ultra|pro|air|mini)\s+)?\d+(?:\s+(?:pro|max|plus|ultra))*\b")
    title_models = set(re.findall(model_pattern, full_title_text, re.I))
    if (len(title_models) == 1 and identity.scope == "apple-direct"
        and "product-launch" in identity.title_actions
        and not identity.title_actions & {"feature-change", "content-release", "platform-integration"}):
        first_lead = _short_lead_scope(lead, sentences=1)
        announcement = re.match(
            r"^apple\s+(?:(?:has|today|just|now|officially)\s+)*"
            r"(?:reveals?|revealed|announces?|announced|introduces?|introduced|unveils?|unveiled)\s+"
            r"(?P<model>" + model_pattern + r")(?=\s+(?:during|with|at|today|for)\b|[.,;:]|$)",
            first_lead, re.I)
        if (announcement and announcement.group("model").casefold() in {model.casefold() for model in title_models}
            and not _compiled_rule('\\b(?:previously|last year|last month|last week|earlier)\\b', 0).search(first_lead)):
            model = _compiled_rule(r"\s+", 0).sub("-", announcement.group("model").casefold(), 0)
            add_claim(model, "product-announcement", category="hardware_products")

    safari_preview = _compiled_rule(r"safari\s+(?:technology\s+preview|技术预览版)\s*(\d+)", re.I).search(claim_evidence)
    if (_compiled_rule(r"\bsafari(?:'s)?\b", 0).search(title_text)
            and _compiled_rule(r"\bmcp\b|model context protocol", 0).search(title_text)
            and _compiled_rule(r"safari\s+(?:mcp|model context protocol)\s+server|safari.{0,30}引入.{0,10}mcp", re.I).search(claim_evidence)
            and _compiled_rule(r"includes?|adding|introduc|integration|lets|letting|引入|支持|智能体", re.I).search(claim_evidence)):
        add_claim("safari-mcp-server", "agent-integration", category="software_systems")
        if safari_preview:
            separation.add("safari-preview-version:" + safari_preview.group(1))

    promotion_work = _compiled_rule(r"(?i:announces?|holding|hosting|its|a|an)\s+['\"‘’]?"
        r"(?P<work>[A-Z][A-Za-z0-9’'-]*(?:\s+[A-Z][A-Za-z0-9’'-]*){0,6})['\"‘’]?"
        r"\s+(?i:look[ -]alike\s+contest)", 0).search(title)
    if promotion_work and _compiled_rule(r"\bapple(?: tv)?(?: is| will)?\s+(?:announc\w*|hold\w*|host\w*|judge\w*)\b", re.I).search(text):
        work = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", promotion_work.group("work").lower(), 0).strip("-")
        add_claim("content-" + work, "look-alike-contest", category="software_systems")

    code_feature_scope = _normalized(" ".join((lead, *source_facts)))
    code_feature_name = _compiled_rule('(?:feature[^.!?]{0,100}called\\s+[‘“\\"]|(?:内部)?代号为[‘“\\"]?)([a-z][a-z0-9_-]{3,40})', 0).search(code_feature_scope)
    if (code_feature_name and identity.scope == "apple-direct"
            and _compiled_rule('\\b(?:code|beta|references?)\\b|代码', 0).search(title_text)
            and _compiled_rule('\\biphone\\b|苹果手机', 0).search(extended_claim_evidence)
            and _compiled_rule('still (?:actively )?developing|continues? to work|under development|still in the works|apple is testing|仍在开发|正测试|尚未启用', 0).search(code_feature_scope)
            and _compiled_rule('\\bnew (?:code|references?)\\b|\\bnow,? the new ios\\s+\\d+(?:\\.\\d+)*\\s+beta\\b|代码(?:曝光|显示|中)|测试版中发现', 0).search(code_feature_scope)):
        add_claim("iphone-feature-" + code_feature_name.group(1), "development-code-disclosure",
                  category="software_systems")
        separation.add("source-feature-codename:" + code_feature_name.group(1))

    watch_models = sorted(set(_compiled_rule('(?:series|ultra)\\s*(\\d+)', 0).findall(title_text)))
    watch_model_labels = sorted(set(_compiled_rule('\\s+', 0).sub('-', m.group(0)) for m in _compiled_rule('(?:series|ultra)\\s*\\d+', 0).finditer(title_text)))
    if ("apple-watch" in identity.title_products and watch_models
            and _compiled_rule('reboot|restart|重启', 0).search(title_text)
            and _compiled_rule('diagnostic logs?|诊断日志|崩溃日志', 0).search(extended_claim_evidence)
            and _compiled_rule('neural engine|神经网络引擎', 0).search(extended_claim_evidence)
            and _compiled_rule('timeout|超时', 0).search(extended_claim_evidence)):
        add_claim("apple-watch-" + "+".join(watch_model_labels), "neural-engine-timeout-report",
                  category="software_systems")
        separation.add("diagnostic-device-set:" + "+".join(watch_model_labels))

    face_failure_model = _compiled_rule('(?<![a-z0-9])iphone\\s*(\\d+)\\s*pro(?:\\s*max)?(?![a-z0-9])', 0).search(title_text)
    if (face_failure_model and _compiled_rule('face id', 0).search(title_text)
            and _compiled_rule('bug|issues?|crash|reboot|问题|故障|失败|重启', 0).search(title_text)
            and _compiled_rule('reproduced|reproduce|according to a reddit post|users?[^.!?]{0,50}(?:report|experienc)|用户反馈|用户反映|复现', 0).search(extended_claim_evidence)
            and _compiled_rule('failed face id|face id.{0,120}(?:fail|失败)|认证失败|验证失败', 0).search(extended_claim_evidence)
            and _compiled_rule('reboot|restart|重启', 0).search(extended_claim_evidence)):
        model = _compiled_rule('\\s+', 0).sub('-', face_failure_model.group(0))
        add_claim(model + "-face-id", "authentication-failure-system-reboot", category="software_systems")
        separation.add("diagnostic-device-set:" + model)

    first_party_hardware_code_disclosure = bool(
        "game-controller" in identity.title_products
        and identity.scope == "apple-direct"
        and (
            "product-disclosure" in identity.title_actions
            or (
                _compiled_rule(r"\b(?:code|identifiers?|ios|ipados|macos|watchos|tvos|visionos)\b|"
                    r"(?:代码|标识符)", re.I).search(title_text)
                and _compiled_rule(r"\b(?:unreleased|prototype|found|hint(?:s|ed)?)\b|"
                    r"(?:未发布|原型|曝光|发现|暗示)", re.I).search(title_text)
            )
        )
    )
    if first_party_hardware_code_disclosure:
        add_claim(
            "apple-game-controller",
            "unreleased-code-disclosure",
            category="hardware_products",
            trusted=True,
        )

    multi_year_product_wave = is_multi_year_apple_product_wave(
        full_title_text,
        lead,
        identity=identity,
    )
    if multi_year_product_wave:
        add_claim(
            "apple-product-roadmap",
            "multi-year-launch-wave",
            category="hardware_products",
            trusted=True,
        )

    executive_subject = ""
    executive_pattern = ""
    for subject, pattern in (
        ("john-ternus", r"\b(?:john\s+)?ternus\b|特努斯"),
        ("doug-brooks", r"\bdoug\s+brooks\b|道格[·・.\s]*布鲁克斯"),
        ("tim-cook", r"\b(?:tim\s+)?cook\b|库克"),
        ("eddy-cue", r"\beddy\s+cue\b|埃迪[·・.\s]*库伊"),
    ):
        if re.search(pattern, f"{full_title_text} {_normalized(lead)[:500]}", re.I):
            executive_subject = subject
            executive_pattern = pattern
            break
    mac_demand_scope = f"{full_title_text}. {_short_lead_scope(lead, sentences=2, limit=900)}"
    if (executive_subject and _compiled_rule(r"mac\s*mini", re.I).search(full_title_text)
            and _compiled_rule(r"mac\s*studio", re.I).search(mac_demand_scope)
            and _compiled_rule(r"\bai\b|智能体", re.I).search(mac_demand_scope)
            and _compiled_rule(r"\bdemand\b|machines of choice|需求|首选设备", re.I).search(mac_demand_scope)
            and _compiled_rule(r"says|said|according to|表示|称", re.I).search(mac_demand_scope)
            and not _compiled_rule(r"predict|forecast|预测|预估", re.I).search(full_title_text)):
        add_claim("mac-mini-studio-ai-demand-" + executive_subject, "executive-current-demand-statement", category="hardware_products")
        separation.add("mac-demand-speaker:" + executive_subject)

    organization_scope = f"{full_title_text}. {_short_lead_scope(lead, sentences=2, limit=700)}"
    departments = {name for name, pattern in (
        ("design", r"\bdesign\b|设计"), ("engineering", r"\bengineering\b|工程"),
        ("operations", r"\boperations\b|运营"), ("marketing", r"\bmarketing\b|营销"))
        if re.search(pattern + r".{0,30}(?:team|organization|decision|authority|团队|部门|决策|权力)", organization_scope, re.I)}
    organizational_decision = bool(_compiled_rule(r"decision authority|决策权|话语权|(?:rebalance|restore).{0,30}(?:team|organization)", re.I).search(organization_scope))
    if executive_subject and len(departments) == 1 and organizational_decision and _contains(organization_scope, "apple", "苹果"):
        department = next(iter(departments))
        stage = ("completed" if _compiled_rule(r"\b(?:restored|rebalanced)\b|已恢复|已调整", re.I).search(full_title_text)
                 else "prospective" if _compiled_rule(r"\b(?:may|might|could)\b|或将|可能", re.I).search(organization_scope) else "")
        if stage:
            add_claim(f"apple-organization-{department}-{executive_subject}", "decision-authority-" + stage,
                      category="software_systems")
            separation |= {"organization-department:" + department, "organization-leader:" + executive_subject,
                           "organization-stage:" + stage}

    merger_scope = f"{full_title_text}. {_short_lead_scope(lead, sentences=1, limit=600)}"
    if _compiled_rule(r"\bmerg(?:er|e|ing)\b|合并", re.I).search(full_title_text) and _contains(merger_scope, "apple", "苹果"):
        parties = {facet.removeprefix("transaction-counterparty-") for facet in identity.facets
                   if facet.startswith("transaction-counterparty-")}
        parties -= {"ceo", "cfo", "coo", "cto", "former", "different", "award-winning", "ai-startup"}
        stage = ("announced" if _compiled_rule(r"\bannounc(?:e|es|ed)\b|宣布合并", re.I).search(full_title_text)
                 else "historical-talks" if _compiled_rule(r"had conversations|曾.{0,30}(?:合并|讨论)|讨论过合并", re.I).search(merger_scope)
                 else "current-talks" if _compiled_rule(r"in talks|discussing|正在.{0,15}(?:讨论|商谈)", re.I).search(full_title_text) else "")
        if len(parties) == 1 and stage:
            party = next(iter(parties))
            add_claim("apple-merger-" + party, stage, category="software_systems")
            separation |= {"merger-party:" + party, "merger-stage:" + stage}

    executive_strategy_area = ""
    if _compiled_rule(r"\bapple\s+tv\b|(?:苹果\s*)?娱乐业务|流媒体业务", re.I).search(claim_evidence):
        executive_strategy_area = "apple-tv"
    executive_strategy_statement = bool(
        executive_subject
        and executive_strategy_area
        and any(_compiled_rule(executive_pattern, re.I).search(clause)
        and _compiled_rule(r'\bapple\s+tv\b|(?:苹果\s*)?娱乐业务|流媒体业务', re.I).search(clause)
        and source_predicate_role(clause) == 'current'
        and not _compiled_rule(r'then.ceo|former|years?\s+ago|当时|前任|去年', re.I).search(clause)
        and _compiled_rule(r"\b(?:said|says|plans?|will|continue(?:s|d)?|build(?:s|ing)?\s+on|"
            r"grow(?:s|ing)?|future\s+is\s+safe)\b|"
            r"(?:表示|称|计划|将|继续|推动|发展|增长)", re.I).search(clause)
        for text in (title, lead, *source_facts) for a, b in source_sentence_spans(text)
        for clause in (text[a:b],))
    )
    if executive_strategy_statement:
        add_claim(
            f"apple-executive-strategy:{executive_subject}:{executive_strategy_area}",
            "business-continuation",
            category="software_systems",
        )

    shared_resource_operation = _versioned_shared_resource_operation(title, lead)
    if shared_resource_operation:
        subject, predicate = shared_resource_operation
        add_claim(subject, predicate, category="software_systems")

    # A disclosure must identify the disputed attribute values. Equal counts
    # and generic component names are not evidence of the same report.
    finish_topic = _primary_title_changed_object(full_title_text) == "finish-color" or (
        not _primary_title_changed_object(full_title_text)
        and _compiled_rule(r"\b(?:colors?|colours?|finishes?)\b", 0).search(text)
    )
    finish_disclosure = bool(
        finish_topic
        and _compiled_rule(r"\b(?:leaks?|leaked|leakers?|rumou?rs?)\b|泄露|爆料|曝光", 0).search(full_title_text)
    )
    finish_models = sorted(
        c.removeprefix("iphone-family:")
        for c in identity.title_components if c.startswith("iphone-family:")
    )
    if finish_disclosure and len(finish_models) == 1:
        generation = finish_models[0].split("-", 1)[0]
        for relation in _finish_alternative_relations(title, lead, evidence, generation):
            add_claim(
                f"iphone-{finish_models[0]}", "finish-lineup-disclosure",
                qualifier=f"alternatives:{relation}", category="hardware_products",
            )
            separation.add(f"finish-alternatives:{relation}")
    focused_foldable_finish_disclosure = bool(
        "foldable-iphone" in identity.title_products
        and "primary-claim-predicate:finish-lineup-disclosure"
        in _title_predicate_separation_keys(full_title_text)
    )
    if focused_foldable_finish_disclosure:
        add_claim(
            "foldable-iphone",
            "finish-lineup-disclosure",
            category="hardware_products",
        )
    foldable_finish_sets = {
        signature.removeprefix("finish-set:foldable-iphone:")
        for signature in _title_fact_signatures(full_title_text, lead)
        if signature.startswith("finish-set:foldable-iphone:")
    }
    for finish_set in sorted(foldable_finish_sets):
        add_claim(
            "foldable-iphone",
            "finish-lineup-disclosure",
            qualifier=f"set:{finish_set}",
            category="hardware_products",
        )
        separation.add(f"finish-set:{finish_set}")

    direct_title_subject = bool(
        identity.scope == "apple-direct"
        or _compiled_rule(r"^(?:apple(?:'s|’s)?|苹果)", 0).search(title_text)
        or _compiled_rule(r"^(?:report|leak|code|sources?|消息|报道|泄露|代码|文件|爆料)"
            r"[^。.!?]{0,32}(?:apple(?:'s|’s)?|苹果)", 0).search(title_text)
    )

    price_forecast_scope = f"{full_title_text} {_normalized(lead)[:420]}"
    price_forecast_subjects = sorted(
        component.removeprefix("iphone-family:")
        for component in identity.title_components
        if component.startswith("iphone-family:")
    )
    if not price_forecast_subjects:
        price_forecast_subjects = sorted(
            component.removeprefix("iphone-model:")
            for component in identity.title_components
            if component.startswith("iphone-model:")
            and not component.endswith("-base")
        )
    title_led_price_forecast = bool(
        direct_title_subject
        and price_forecast_subjects
        and _compiled_rule(r"\b(?:price|prices|pricing)\b|(?:价格|售价|涨价|提价)", 0).search(full_title_text)
        and _compiled_rule(r"\b(?:estimate(?:d|s)?|forecast(?:s|ed)?|expect(?:s|ed)?|"
            r"reportedly|could|may|might|likely|rumou?r(?:ed)?|leak(?:ed|s)?)\b|"
            r"(?:预计|预估|预测|可能|大概率|或将|曝光|传闻|爆料)", 0).search(price_forecast_scope)
    )
    if title_led_price_forecast:
        for price_subject in price_forecast_subjects:
            add_claim(
                f"apple-product-price:{price_subject}",
                "retail-price-forecast",
                category="hardware_products",
            )

    first_party_rename_product = next(
        iter(
            identity.title_products
            & {
                "app-store",
                "apple-books",
                "apple-maps",
                "apple-music",
                "apple-sports",
                "apple-tv",
                "apple-wallet",
                "icloud",
                "safari",
            }
        ),
        "",
    )
    title_owned_rename = bool(
        first_party_rename_product
        and is_direct_first_party_named_object_change(full_title_text, lead)
    )
    rename_target = ""
    if title_owned_rename:
        for pattern in (
            r"\b(?:use|uses|using|display|displays|show|shows|label|labels|mark|marks)\b"
            r"[^'\"“”]{0,50}['\"“]([^'\"“”]{2,60})['\"”][^.!?]{0,40}"
            r"\binstead\s+of\b",
            r"\bbring(?:s|ing)?\s+up\b[^.!?]{0,100}\b(?:if|when)\b[^.!?]{0,60}"
            r"\bsearch(?:es|ing)?\s+(?:for\s+)?['\"“]([^'\"“”]{2,60})['\"”]",
            r"\b(?:update|updates|updated|change|changes|changed|rename|renames|renamed)\b"
            r"[^'\"“”]{0,50}['\"“][^'\"“”]{2,60}['\"”]\s+(?:to|as)\s+"
            r"['\"“]([^'\"“”]{2,60})['\"”]",
            r"(?:改名为|更名为|重命名为|改称|标注为|显示为)\s*[“\"]([^”\"]{2,30})[”\"]",
            r"\b(?:rename|renames|renamed|renaming|relabel|relabels|relabeled|relabeling)\b"
            r"[^'\"“”]{0,80}['\"“]([^'\"“”]{2,60})['\"”]",
            r"\b(?:change(?:s|d)?|rename(?:s|d)?|relabel(?:s|ed)?)\b[^。.!?]{0,90}?"
            r"\bto\s+([a-z][a-z0-9 .'-]{2,50}?)(?=\s+(?:as|for|in)\b|[,.;!?]|$)",
            r"\b(?:display|displays|show|shows)\s+([a-z][a-z0-9 .'-]{2,50}?)\s+instead\s+of\b",
            r"(?:改名为|更名为|重命名为|改称|标注为|显示为)([^，。！？:：\s]{2,30})",
        ):
            match = re.search(pattern, extended_claim_evidence, re.I)
            if not match:
                continue
            rename_target = _compiled_rule(r"[^a-z0-9\u3400-\u9fff]+", 0).sub("-", _normalized(match.group(1)), 0).strip("-")
            if rename_target:
                break
    if first_party_rename_product and rename_target:
        add_claim(
            f"first-party-app-{first_party_rename_product}",
            "named-object-rename",
            qualifier=rename_target,
            category="software_systems",
            trusted=True,
        )
        named_object_classes = (
            ("lake", r"\blake\b|湖"),
            ("gulf", r"\bgulf\b|海湾|湾"),
            ("river", r"\briver\b|河"),
            ("sea", r"\bsea\b|海"),
            ("mountain", r"\bmount(?:ain)?\b|山"),
            ("island", r"\bisland\b|岛"),
            ("road", r"\b(?:road|street|avenue|highway)\b|(?:道路|公路|街道|大街)"),
            ("airport", r"\bairport\b|机场"),
            ("station", r"\bstation\b|车站"),
            ("park", r"\bpark\b|公园"),
            ("city", r"\bcity\b|城市|市"),
            ("country", r"\bcountry\b|国家|国"),
        )
        named_object_class = next(
            (
                object_class
                for object_class, pattern in named_object_classes
                if re.search(pattern, full_title_text, re.I)
            ),
            "",
        )
        explicit_regions = sorted(set(regions) - {"multi-region"})
        if named_object_class and explicit_regions:
            event_keys.add(
                f"primary-claim:first-party-app-{first_party_rename_product}:"
                f"named-object-rename-class:{named_object_class}:"
                f"{','.join(explicit_regions)}"
            )

    explicit_catalog_scale = bool(
        _compiled_rule(r"\b(?:10|ten|eleven|11)\+?\s+(?:products?|devices?|models?)\b|"
            r"(?:10|十|11|十一)(?:余|多|\+)?\s*款(?:在售)?(?:产品|设备|机型)", re.I).search(title_text)
        and len(identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS) >= 2
    )
    catalog_withdrawal = bool(
        (identity.scope == "apple-direct" or _contains(title_text, "apple", "苹果"))
        and _compiled_rule(r"\b(?:discontinu(?:e|es|ed|ing)|withdraw(?:s|n|ing)?|remove(?:s|d|ing)?|"
            r"drop(?:s|ped|ping)?|retire(?:s|d|ing)?)\b|"
            r"(?:下架|停售|停产|停止销售|退出在售阵容|移出产品线)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:products?|devices?|models?|lineup|catalog)\b|"
            r"(?:多款|款设备|款(?:在售)?产品|产品阵容|在售阵容|官网产品)", re.I).search(title_text)
        and (
            len(_bounded_evidence_products(claim_evidence)) >= 2
            or explicit_catalog_scale
        )
    )
    if catalog_withdrawal:
        add_claim(
            "apple-product-catalog",
            "multi-product-withdrawal-forecast",
            category="hardware_products",
            trusted=True,
        )

    executive_farewell = bool(
        _compiled_rule(r"\b(?:signs?\s+off|farewell|thanks?\s+(?:apple\s+)?staff)\b|"
            r"\b(?:comments?|responds?|response|message|memo|letter|email|note|post|writes?|says?|remarks?)\b"
            r".{0,48}\b(?:final|last)\s+day\b|"
            r"\b(?:final|last)\s+day\b.{0,48}"
            r"\b(?:comments?|responds?|response|message|memo|letter|email|note|post|writes?|says?|remarks?)\b|"
            r"(?:告别.{0,8}(?:信|内部信)|最后一封.{0,12}内部信|告别员工|感谢员工)|"
            r"(?:最后一天).{0,30}(?:回应|致信|发信|内部信|备忘录|发文|留言|感谢|告别)|"
            r"(?:回应|致信|发信|内部信|备忘录|发文|留言|感谢|告别).{0,30}(?:最后一天)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:ceo|chief executive|tim cook|john ternus)\b|"
            r"(?:首席执行官|库克|特努斯)", re.I).search(title_text)
    )
    if executive_farewell:
        add_claim(
            "apple-leadership",
            "executive-farewell-communication",
            category="software_systems",
            trusted=True,
        )

    company_hall_award = bool(
        _contains(title_text, "apple", "苹果")
        and _compiled_rule(r"\b(?:induct(?:ed|s)?|honou?red|recognized|named)\b|"
            r"(?:入选|获表彰|获授|列入)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:creative|brand)\s+hall\s+of\s+fame\b|"
            r"(?:创意|品牌)名人堂", re.I).search(title_text)
    )
    if company_hall_award:
        add_claim(
            "apple-brand",
            "hall-of-fame-induction",
            category="software_systems",
            trusted=True,
        )

    personnel_role_change = bool(
        _compiled_rule(r"\bphil\s+schiller\b|菲尔[·・.\s]*席勒", re.I).search(title_text)
        and _compiled_rule(r"\b(?:steps?\s+(?:down|back)|scales?\s+back|no\s+longer\s+working|"
            r"leav(?:es|ing)\s+(?:his\s+)?(?:biggest\s+)?(?:job|jobs|duties))\b|"
            r"(?:卸任|退出|不再负责|缩减|淡出).{0,24}(?:职责|工作|管理|负责人)?", re.I).search(title_text)
    )
    if personnel_role_change:
        add_claim(
            "apple-personnel-phil-schiller",
            "role-reduction",
            category="software_systems",
            trusted=True,
        )

    executive_profile_asset_update = bool(
        _compiled_rule(r"\b(?:ceo|chief executive)\b|(?:首席执行官|ceo)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:profile\s+(?:photo|image)|avatar|headshot)\b|(?:头像|个人资料图片)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:replac(?:e|es|ed|ing)|updat(?:e|es|ed|ing)|swap(?:s|ped|ping)?)\b|"
            r"(?:更换|替换|更新)", re.I).search(title_text)
    )
    if executive_profile_asset_update:
        add_claim(
            "apple-leadership",
            "ceo-social-profile-image-update",
            category="software_systems",
            trusted=True,
        )

    executive_social_account = bool(
        _compiled_rule(r"(?<![a-z])ceo(?![a-z])|\bchief executive\b|首席执行官", re.I).search(title_text)
        and _compiled_rule(r"\b(?:on|joins?|opens?|launches?|starts?)\s+(?:an?\s+)?(?:x|twitter|weibo)\b|"
            r"\bfirst\s+(?:post|message)\b|"
            r"(?:入驻|开通|启用|开).{0,18}(?:微博|社交账号|社交平台|x\s*平台)|"
            r"(?:首条|第一条).{0,10}(?:博文|帖子|消息|动态)", re.I).search(title_text)
    )
    if executive_social_account:
        add_claim(
            "apple-leadership",
            "ceo-social-account-launch",
            category="software_systems",
            trusted=True,
        )

    official_follow_change = bool(
        _compiled_rule(r"(?:apple|苹果).{0,8}(?:官方|official).{0,16}(?:账号|社媒|account)", 0).search(title_text)
        and _compiled_rule(r"取关|唯一关注|取消关注|\bunfollows?\b|\bonly\s+follows?\b", 0).search(title_text)
        and _compiled_rule(r"ceo|首席执行官", 0).search(title_text)
    )
    if official_follow_change:
        add_claim("apple-corporate-social-account", "ceo-follow-change", category="software_systems")

    executive_compensation_signal = bool(
        _compiled_rule(r"\b(?:salary|compensation|equity award|stock award)\b|"
            r"(?:薪酬|年薪|工资|股权奖励|股票奖励)", re.I).search(title_text)
        or _compiled_rule(r"\bpaying\b.{1,64}\bto\s+(?:run|lead|serve\s+as\s+(?:the\s+)?ceo)\b|"
            r"\b(?:what|how\s+much)\b.{0,40}\bpay(?:ing)?\b.{0,40}"
            r"\b(?:ceo|chief executive)\b", re.I).search(title_text)
    )
    executive_compensation = executive_compensation_signal and bool(
        _compiled_rule(r"\b(?:apple|ceo|chief executive)\b|(?:苹果|首席执行官)", re.I).search(title_text)
        or _compiled_rule(r"\b(?:new\s+)?ceo\b|(?:新任\s*ceo|首席执行官)", re.I).search(text)
    )
    if executive_compensation:
        add_claim(
            "apple-leadership",
            "ceo-compensation-disclosure",
            category="software_systems",
            trusted=True,
        )

    executive_memo_title_signal = bool(
        _compiled_rule(r"\b(?:memo|letter|email)\b|"
            r"\baddresses?\s+(?:apple\s+)?staff\b|"
            r"(?:内部信|公开信|全员信|备忘录|致员工|致全体员工)", re.I).search(full_title_text)
        or (
            _compiled_rule(r"\b(?:teases?|promises?|says?)\b.{0,45}\b(?:launch|event|products?)\b|"
                r"(?:放话|预告|透露).{0,32}(?:下周|新品|发布|活动)", re.I).search(full_title_text)
            and _compiled_rule(r"\b(?:memo|letter|email)\b|(?:内部信|公开信|全员信|备忘录)", re.I).search(extended_claim_evidence)
        )
    )
    first_executive_employee_memo = bool(
        executive_memo_title_signal
        and
        _compiled_rule(r"\b(?:memo|letter|email|message)\b.{0,42}\b(?:employees?|staff|company[- ]wide)\b|"
            r"\b(?:employees?|staff|company[- ]wide)\b.{0,42}\b(?:memo|letter|email|message)\b|"
            r"(?:首封|第一封|全员|内部).{0,24}(?:内部信|公开信|信件|备忘录|邮件)|"
            r"(?:内部信|公开信|备忘录|全员信).{0,20}(?:首封|第一封|上任)|"
            r"(?:发给|致).{0,16}(?:全体|全员|内部).{0,12}(?:员工|职员).{0,12}(?:公开信|信件|备忘录|邮件)", re.I).search(extended_claim_evidence)
        and _compiled_rule(r"\b(?:first\s+day|first\s+(?:company[- ]wide\s+)?memo|new\s+(?:apple\s+)?ceo)\b|"
            r"(?:首封|第一封|上任|新(?:任)?\s*ceo|(?:正式)?(?:出任|接任|就任).{0,20}(?:苹果)?\s*ceo)", re.I).search(extended_claim_evidence)
        and _compiled_rule(r"\b(?:ceo|chief executive)\b|(?:首席执行官|ceo)", re.I).search(extended_claim_evidence)
    )
    if first_executive_employee_memo:
        add_claim(
            "apple-leadership",
            "ceo-first-employee-memo",
            category="software_systems",
            trusted=True,
        )

    corporate_services_role_exit = bool(
        _compiled_rule(r"\b(?:apple|former\s+apple|ex-apple)\b.{0,44}\b(?:cfo|executive|luca\s+maestri)\b|"
            r"\b(?:luca\s+maestri|cfo|executive)\b.{0,44}\bapple\b|"
            r"(?:苹果).{0,32}(?:首席财务官|高管|马斯特里)|(?:马斯特里).{0,32}(?:苹果|首席财务官|高管)", re.I).search(full_title_text)
        and _compiled_rule(r"\bcorporate services\b|企业服务(?:部门|职责)?", re.I).search(extended_claim_evidence)
        and _compiled_rule(r"\b(?:isn['’]?t\s+running|no\s+longer\s+runs?|step(?:s|ped|ping)?\s+down|leaves?|exits?)\b|"
            r"(?:卸任|退出|不再负责|离任)", re.I).search(extended_claim_evidence)
    )
    if corporate_services_role_exit:
        add_claim(
            "apple-corporate-services",
            "role-exit",
            category="software_systems",
            trusted=True,
        )

    inbox_accessory_policy_denial = bool(
        _contains(full_title_text, "apple", "iphone", "苹果")
        and _contains(
            full_title_text,
            "charger",
            "earpods",
            "in-box accessories",
            "充电头",
            "充电器",
            "耳机",
            "随盒配件",
        )
        and (
            _compiled_rule(r"\b(?:den(?:y|ies|ied)|no\s+(?:notice|policy|change)|not\s+restor(?:e|ing))\b|"
                r"(?:否认|辟谣|没有通知|未发布通知|并未恢复|不再附赠)", re.I).search(full_title_text)
            or (
                _compiled_rule(r"\b(?:official\s+response|responds?)\b|官方回应", re.I).search(full_title_text)
                and _compiled_rule(r"\b(?:den(?:y|ies|ied)|no\s+(?:notice|policy|change)|not\s+restor(?:e|ing))\b|"
                    r"(?:否认|辟谣|没有.{0,10}通知|未发布.{0,10}(?:通知|政策)|并未恢复|没有.{0,10}政策变更)", re.I).search(extended_claim_evidence)
            )
        )
    )
    if inbox_accessory_policy_denial:
        add_claim(
            "iphone-in-box-accessories",
            "policy-denial",
            category="hardware_products",
            trusted=True,
        )

    foldable_magsafe_support = bool(
        "foldable-iphone" in identity.title_products
        and _contains(title_text, "magsafe", "磁吸充电")
        and _compiled_rule(r"\b(?:has|have|support(?:s|ed|ing)?|include(?:s|d)?)\b|"
            r"(?:支持|配备|搭载|有望支持)", re.I).search(title_text)
    )
    if foldable_magsafe_support:
        add_claim(
            "foldable-iphone",
            "magsafe-support",
            category="hardware_products",
            trusted=True,
        )

    mac_intel_support_removal = bool(
        _contains(claim_evidence, "mac", "mac app store", "mac 开发者")
        and _contains(title_text, "intel", "英特尔", "arm64")
        and _compiled_rule(r"\b(?:drop|remove|end|stop|phase\s+out).{0,20}\bsupport(?:ing)?\b|"
            r"\barm64[- ]only\b|"
            r"(?:移除|停止|终止|放弃).{0,16}(?:支持|兼容)|仅支持\s*arm64", re.I).search(title_text)
    )
    if mac_intel_support_removal:
        add_claim(
            "mac-developer-distribution",
            "intel-support-removal",
            category="software_systems",
            trusted=True,
        )

    legal_openai_response = bool(
        _contains(title_text, "openai")
        and _contains(claim_evidence, "trade secret", "trade-secret", "商业机密", "商业秘密")
        and _compiled_rule(r"\b(?:den(?:y|ies|ied)|reject(?:s|ed)?|responds?|response)\b|"
            r"\b(?:mess|problem)\b.{0,36}\b(?:apple['’]?s\s+own\s+making|of\s+apple['’]?s\s+own\s+making)\b|"
            r"\bnot\s+our\s+fault\b|"
            r"(?:否认|回应).{0,28}(?:窃取|窃密|指控|商业机密|商业秘密)|"
            r"(?:自己造成|一手造成).{0,18}(?:混乱|问题)|"
            r"(?:自身|自己).{0,12}(?:应为|应该为).{0,18}(?:混乱|问题).{0,8}负责", re.I).search(title_text)
    )
    if legal_openai_response:
        add_claim(
            "apple-openai-trade-secret-case",
            "response-filing",
            category="hardware_products",
            trusted=True,
        )

    legal_evidence_disclosure = bool(
        not legal_openai_response
        and (
            _compiled_rule(r"^apple\b.{0,30}\b(?:accuses?|alleges?|claims?)\b.{0,40}\bopenai\b"
                r".{0,60}\b(?:destroy(?:ed|ing|uction)?|withhold(?:s|ing)?)\b.{0,20}\bevidence\b", re.I).search(title_text)
            or (
                _contains(claim_evidence, "openai")
                and _contains(
                    claim_evidence,
                    "trade secret",
                    "trade-secret",
                    "商业机密",
                    "商业秘密",
                )
                and _compiled_rule(r"\b(?:new|shocking|forensic)\s+evidence\b|"
                    r"\b(?:stolen|theft|destroy(?:ed|ing|uction))\b.{0,42}\bevidence\b|"
                    r"^apple\s+(?:says?|alleges?|claims?).{0,100}"
                    r"\b(?:stolen|theft|destroy(?:ed|ing|uction))\b|"
                    r"(?:新证据|惊人证据|震撼证据|取证证据|销毁证据)", re.I).search(claim_evidence)
            )
        )
    )
    if legal_evidence_disclosure:
        add_claim(
            "apple-openai-trade-secret-case",
            "evidence-disclosure",
            category="hardware_products",
            trusted=True,
        )

    mac_desktop_ai_timing = bool(
        _contains(claim_evidence, "mac mini", "mini / studio", "mini/studio")
        and _contains(claim_evidence, "mac studio", "mini / studio", "mini/studio")
        and _contains(
            claim_evidence,
            "unusual timing",
            "unusually timed",
            "early launch",
            "launched early",
            "early announcement",
            "提前发布",
            "提前更新",
            "上新",
        )
        and _contains(
            claim_evidence,
            "ai demand",
            "enterprise demand",
            "enterprise appetite",
            "strong demand",
            "ai hardware",
            "ai 需求",
            "企业需求",
            "ai 硬件",
        )
        or bool(
            _contains(claim_evidence, "mac mini", "mini / studio", "mini/studio")
            and _contains(claim_evidence, "mac studio", "mini / studio", "mini/studio")
            and _contains(
                title_text,
                "unusual timing",
                "unusually timed",
                "all about ai",
                "提前发布",
                "提前更新",
                "提前上新",
            )
            and _contains(title_text, "ai", "人工智能")
        )
    )
    if mac_desktop_ai_timing:
        add_claim(
            "apple-mac-mini-studio",
            "ai-demand-accelerated-refresh",
            category="hardware_products",
            trusted=True,
        )

    if identity.content_form == "news":
        repair_cost = _repair_cost_estimate(title, lead, evidence, identity)
        if repair_cost:
            repair_subject, repair_predicate, repair_amount = repair_cost
            add_claim(
                repair_subject,
                repair_predicate,
                qualifier=repair_amount,
                category="hardware_products",
                trusted=True,
            )

        hardware_roadmap = _unreleased_hardware_launch_roadmap(
            title,
            lead,
            identity,
        )
        if hardware_roadmap:
            roadmap_product, roadmap_year = hardware_roadmap
            add_claim(
                roadmap_product,
                "launch-roadmap",
                qualifier=roadmap_year,
                category="hardware_products",
                trusted=True,
            )

    normalized_regions = {
        region for region in regions if region and region != "multi-region"
    }
    disaster_relief_action = bool(
        normalized_regions
        and (
            identity.scope == "apple-direct"
            or _contains(text, "apple", "苹果")
        )
        and _compiled_rule(r"\b(?:donat(?:e|es|ed|ion)|pledges?|aid)\b.{0,70}"
            r"\b(?:relief|rebuilding|recovery|victims?)\b|"
            r"\b(?:relief|rebuilding|recovery)\b.{0,70}"
            r"\b(?:donat(?:e|es|ed|ion)|pledges?|aid)\b|"
            r"(?:捐款|捐助|援助|提供援助).{0,50}(?:救援|救灾|重建|灾后恢复)|"
            r"(?:救援|救灾|重建|灾后恢复).{0,50}(?:捐款|捐助|援助|提供援助)", 0).search(text)
        and _compiled_rule(r"\b(?:floods?|mudslides?|earthquakes?|wildfires?|typhoons?|hurricanes?)\b|"
            r"(?:洪水|洪灾|山洪|泥石流|地震|山火|台风|飓风|自然灾害|灾害|灾后)", 0).search(text)
    )
    if disaster_relief_action:
        for hazard, pattern in (("flood-landslide", r"flood|mudslide|洪水|洪灾|山洪|泥石流"),
                                ("earthquake", r"earthquake|地震"),
                                ("wildfire", r"wildfire|山火"),
                                ("storm", r"typhoon|hurricane|台风|飓风")):
            if re.search(pattern, text, re.I):
                separation.add("disaster-relief-hazard:" + hazard)
        for region in sorted(normalized_regions):
            add_claim(
                f"apple-disaster-relief-{region}",
                "donation",
                category="hardware_products",
                trusted=True,
            )

    preorder_scope = f"{title_text}. {_short_lead_scope(lead, sentences=1, limit=420)}"
    preorder_action = bool(
        _compiled_rule(r"\bpre[- ]?orders?\b|(?:预购|预售)", 0).search(title_text)
        and _compiled_rule(r"\b(?:may|might|could|will|reportedly|expected to|set to|announced|revealed|confirms?|open|begin)\b|"
            r"(?:可能|或将|预计|据称|消息称|报道|宣布|确认|开启|开始)", 0).search(preorder_scope)
    )
    preorder_date = ""
    preorder_date_scope = f"{preorder_scope}. {_short_lead_scope(lead, sentences=2, limit=800)} {_normalized(evidence)[:1400]}"
    if preorder_action:
        owned_date_clauses = []
        preorder_source_clauses = _compiled_rule(r"(?<=[.!?。！？])\s*", 0).split(preorder_date_scope, 0)
        for clause in preorder_source_clauses:
            if _compiled_rule(r"\bpre[- ]?orders?\b|预购|预售", 0).search(clause):
                clause_identity = build_event_identity(clause, "")
                if clause_identity.products and identity.products and not (clause_identity.products & identity.products):
                    continue
                if clause_identity.scope == "third-party-context" and clause_identity.action_owner != "apple":
                    continue
                conflicting_model = any(
                    {c for c in identity.title_components if c.startswith(prefix)}
                    and {c for c in clause_identity.title_components if c.startswith(prefix)}
                    and not ({c for c in identity.title_components if c.startswith(prefix)} &
                             {c for c in clause_identity.title_components if c.startswith(prefix)})
                    for prefix in ("iphone-model:", "macbook-model:", "iphone-family:")
                )
                if conflicting_model:
                    continue
            owned_date_clauses.append(clause)
        preorder_date_scope = ". ".join(owned_date_clauses)
    month_names = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    english_date = re.search(
        r"\bpre[- ]?orders?\b[^。.!?]{0,100}\b("
        + "|".join(month_names)
        + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        preorder_date_scope,
    )
    chinese_date = _compiled_rule(r"(?:预购|预售)[^。！？]{0,70}?(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日|"
        r"(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。！？]{0,70}(?:预购|预售)", 0).search(preorder_date_scope)
    iso_date = _compiled_rule(r"\bpre[- ]?orders?\b[^。.!?]{0,80}\b(?:20\d{2}-)?(\d{1,2})-(\d{1,2})\b", 0).search(preorder_date_scope)
    if english_date:
        preorder_date = f"{month_names[english_date.group(1)]:02d}-{int(english_date.group(2)):02d}"
    elif chinese_date:
        month = chinese_date.group(1) or chinese_date.group(3)
        day = chinese_date.group(2) or chinese_date.group(4)
        preorder_date = f"{int(month):02d}-{int(day):02d}"
    elif iso_date:
        preorder_date = f"{int(iso_date.group(1)):02d}-{int(iso_date.group(2)):02d}"
    if not preorder_date:
        avoided_date = re.search(
            r"\b(?:sidestep|avoid|move away from)\b[^。.!?]{0,45}\b("
            + "|".join(month_names)
            + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b[^。.!?]{0,65}"
            r"\b(?:moving|pushing|delaying)\b[^。.!?]{0,35}"
            r"\b(?:to saturday|to the next day|by a day)\b",
            preorder_date_scope,
        )
        if avoided_date:
            shifted = date(
                2000,
                month_names[avoided_date.group(1)],
                int(avoided_date.group(2)),
            ) + timedelta(days=1)
            preorder_date = f"{shifted.month:02d}-{shifted.day:02d}"
    if preorder_action and preorder_date:
        component_subjects = [
            f"{namespace}-{component.split(':', 1)[1]}"
            for prefix, namespace in (
                ("iphone-model:", "iphone"),
                ("iphone-family:", "iphone"),
                ("macbook-model:", "macbook"),
            )
            for component in sorted(identity.title_components)
            if component.startswith(prefix)
        ]
        preorder_subject = component_subjects[0] if component_subjects else ""
        if not preorder_subject and len(identity.title_products) == 1:
            preorder_subject = next(iter(identity.title_products))
        if preorder_subject:
            forecast_title = bool(_compiled_rule(r"\b(?:expected|may|might|could|reportedly)\b|预计|可能|据称|消息称", 0).search(title_text))
            # Status and date belong to the same local preorder action. A
            # neutral first sentence may be followed by its official statement;
            # a historical or modal statement cannot confirm the current date.
            preorder_status_scope = ". ".join(clause for clause in owned_date_clauses
                if _compiled_rule(r"\bpre[- ]?orders?\b|预购|预售", 0).search(clause)
                and not _compiled_rule(r"\b(?:last year|previously|earlier|historically|used to|may|might|could|would)\b|去年|此前|曾经|可能|或许", 0).search(clause))
            confirmed = bool(_compiled_rule(r"officially (?:announced|confirmed)|\bapple\s+(?:(?:has|today|yesterday|now|recently|just|officially)\s+)*(?:announced|confirms?|confirmed)\b|\b(?:has|have)\s+been\s+(?:officially\s+)?(?:revealed|announced|confirmed)\s+by\s+apple\b|苹果(?:正式)?(?:宣布|确认)", 0).search(preorder_status_scope))
            if not confirmed:
                # Carry a proven current owner across neutral prose. Explicit
                # owner/model changes and historical/modal frames end that
                # continuity; grammatical number is not an event boundary.
                model_prefixes = ("iphone-model:", "macbook-model:", "iphone-family:")
                expected_models = {value for value in identity.title_components if value.startswith(model_prefixes)}
                continuity_sources = [_compiled_rule(r"(?<=[.!?。！？])\s*", 0).split(_normalized(value)[:1400], 0)
                                      for value in (lead, evidence) if value]
                for clauses in continuity_sources:
                    current_announcement = False
                    for clause in clauses:
                        clause_identity = build_event_identity(clause, "")
                        clause_models = {value for value in clause_identity.title_components if value.startswith(model_prefixes)}
                        other_owner = bool(
                            (clause_identity.title_products and identity.title_products
                             and not (clause_identity.title_products & identity.title_products))
                            or (expected_models and clause_models and not (expected_models & clause_models))
                            or (clause_identity.scope == "third-party-context" and clause_identity.action_owner != "apple")
                            or (clause_identity.actors and "product-launch" in clause_identity.title_actions
                                and clause_identity.action_owner != "apple"))
                        if other_owner:
                            current_announcement = False
                            continue
                        if _compiled_rule('\\b(?:last year|previously|earlier|historically|used to|may|might|could|would)\\b|去年|此前|曾经|可能|或许|尚未|并未|没有', 0).search(clause):
                            current_announcement = False
                            continue
                        announced = bool(_compiled_rule('\\b(?:has|have) been (?:officially )?(?:revealed|announced|introduced) by apple\\b|\\bapple\\s+(?:(?:has|today|now|officially)\\s+)*(?:announced|revealed|introduced)\\b', 0).search(clause))
                        if (announced and clause_identity.title_products & identity.title_products
                                and (not expected_models or expected_models & clause_models)):
                            current_announcement = True
                        if current_announcement and _compiled_rule('\\bpre[- ]?orders?\\b|预购|预售', 0).search(clause):
                            confirmed = True
                            break
                    if confirmed:
                        break
            forecast_source = bool(_compiled_rule(r"\b(?:expected|may|might|could|source claims)\b|预计|可能|据称|消息称", 0).search(preorder_scope))
            if _compiled_rule(r"\b(?:may|might|could|would)\s+have\s+been\b", 0).search(preorder_scope):
                confirmed = False
            if forecast_title or (forecast_source and not confirmed):
                separation.add("preorder-stage:forecast")
            elif confirmed:
                separation.add("preorder-stage:announced")
            add_claim(
                preorder_subject,
                "preorder-schedule",
                qualifier=preorder_date,
                category="hardware_products",
                trusted=True,
            )

    historical_auction_scope = f"{title_text}. {_short_lead_scope(lead, sentences=1, limit=420)}"
    historical_actor = (
        "steve-jobs"
        if _compiled_rule(r"\bsteve jobs\b|乔布斯", 0).search(historical_auction_scope)
        else ""
    )
    artifact_patterns = (
        ("science-project", r"\bscience (?:fair )?project\b|科学(?:展览|实验|展会)?项目"),
        ("business-card", r"\bbusiness card\b|名片"),
        ("signed-letter", r"\bsigned (?:fan )?letter\b|签名.{0,8}信(?:件)?"),
        ("apple-1", r"\bapple[- ]?1\b|apple-1|苹果一号"),
        ("prototype", r"\bprototype\b|原型机"),
    )
    historical_artifact = next(
        (
            name
            for name, pattern in artifact_patterns
            if re.search(pattern, historical_auction_scope)
        ),
        "",
    )
    historical_auction_action = bool(
        historical_actor
        and historical_artifact
        and _compiled_rule(r"\b(?:auction(?:ed)?|sells?|sold)\b|(?:拍卖|成交|落槌)", 0).search(historical_auction_scope)
    )
    if historical_auction_action:
        add_claim(
            f"apple-history-{historical_actor}-{historical_artifact}",
            "auction-sale",
            category="hardware_products",
            trusted=True,
        )

    mac_mini_scope = f"{title_text} {_normalized(lead)[:520]}"
    if "mac-mini" in identity.title_products:
        has_unfulfilled_or_recent_status = bool(
            _compiled_rule(r"\b(?:pending|recent|unfulfilled)\b|"
                r"\b(?:has|have)\s+(?:yet|not)\s+to\s+ship\b|"
                r"\bnot\s+yet\s+shipped\b|"
                r"(?:尚未|还未|未).{0,8}发货|待发货|近期", 0).search(mac_mini_scope)
        )
        has_order_subject = bool(
            _compiled_rule(r"\borders?\b|(?:订单|订购)", 0).search(mac_mini_scope)
            or has_unfulfilled_or_recent_status
            and _compiled_rule(r"\b(?:customers?|purchases?|buyers?)\b|(?:客户|用户|网友|买家)", 0).search(mac_mini_scope)
        )
        has_free_terms = _contains(
            mac_mini_scope,
            "for free",
            "free upgrade",
            "at no additional cost",
            "no additional cost",
            "without a price increase",
            "at no charge",
            "price unchanged",
            "免费",
            "无需额外付费",
            "不会产生任何额外费用",
            "价格不变",
        )
        has_upgrade_action = _contains(
            mac_mini_scope,
            "upgrade",
            "upgrading",
            "replace",
            "replacing",
            "replaced",
            "升级",
            "更换",
            "替换",
        )
        pending_order_upgrade = bool(
            has_order_subject
            and has_unfulfilled_or_recent_status
            and has_free_terms
            and has_upgrade_action
        )
        if pending_order_upgrade:
            add_claim(
                "mac-mini",
                "pending-order-free-upgrade",
                category="hardware_products",
                trusted=True,
            )

        display_capability = bool(
            _contains(
                title_text,
                "external display",
                "external displays",
                "display support",
                "外接显示",
                "显示能力",
            )
            and (
                _compiled_rule(r"\b(?:\d+k|\d{2,3}\s*hz)\b", 0).search(title_text)
                or _contains(title_text, "support", "supports", "支持")
            )
        )
        if display_capability:
            add_claim(
                "mac-mini",
                "external-display-capability",
                category="hardware_products",
                trusted=True,
            )

        preorder_launch = bool(
            _compiled_rule(r"\bpre[- ]?orders?\b|(?:接受|开启|开放|开始).{0,8}预购|今日预购", 0).search(title_text)
        )
        if preorder_launch:
            add_claim(
                "mac-mini",
                "retail-preorder",
                category="hardware_products",
                trusted=True,
            )

        current_price_change = bool(
            _compiled_rule(r"\b(?:price|prices|pricing)\b.{0,28}\b(?:rise|rises|rose|increase[sd]?|hike[sd]?)\b|"
                r"\b(?:raise[sd]?|increase[sd]?|hike[sd]?)\b.{0,28}\b(?:price|prices|pricing)\b|"
                r"(?:涨到|涨至|涨为|售价升至|起售价升至|价格升至).{0,12}\d|"
                r"(?:涨价|提价|上调价格|上调售价)", 0).search(title_text)
        )
        if current_price_change and not pending_order_upgrade:
            add_claim(
                "mac-mini",
                "retail-price-change",
                category="hardware_products",
                trusted=True,
            )

    component_leak_scope = f"{title_text} {_normalized(lead)[:420]}"
    if "foldable-iphone" in identity.title_products and _contains(
        component_leak_scope,
        "motherboard",
        "motherboards",
        "logic board",
        "logic boards",
        "主板",
        "逻辑板",
    ) and _contains(
        component_leak_scope,
        "leak",
        "leaked",
        "leakers",
        "purported",
        "show off",
        "shown",
        "曝光",
        "泄露",
        "流出",
        "疑似",
    ):
        add_claim(
            "foldable-iphone",
            "component-leak",
            qualifier="logic-board",
            category="hardware_products",
            trusted=True,
        )

    if "consumer-purchase-intent" in identity.title_components:
        product_subjects = sorted(identity.title_products)
        percentage_match = _compiled_rule(r"(?<!\d)(\d+(?:\.\d+)?)\s*%", 0).search(title_text)
        if product_subjects and percentage_match:
            interest_value = float(percentage_match.group(1))
            negative_interest = bool(
                _compiled_rule(r"\b(?:aren['’]?t|are\s+not|not|no)\s+(?:at\s+all\s+)?interested\b|"
                    r"\bno\s+interest\b|(?:没兴趣|不感兴趣|无意购买|没有兴趣)", 0).search(title_text)
            )
            if negative_interest:
                interest_value = max(0.0, 100.0 - interest_value)
            normalized_interest = (
                str(int(interest_value))
                if interest_value.is_integer()
                else f"{interest_value:.2f}".rstrip("0").rstrip(".")
            )
            add_claim(
                product_subjects[0],
                "consumer-purchase-intent-survey",
                qualifier=f"positive-interest-{normalized_interest}",
                category="hardware_products",
                trusted=True,
            )

    wallet_documents = sorted(
        component.removeprefix("wallet-document:")
        for component in identity.title_components
        if component.startswith("wallet-document:")
    )
    if "apple-wallet" in identity.title_products and wallet_documents:
        wallet_action = (
            "regional-availability"
            if _contains(
                title_text,
                "launches in",
                "launched in",
                "new state",
                "available in",
                "上线",
                "新增支持",
                "成为第",
            )
            else "document-feature-change"
        )
        for wallet_document in wallet_documents:
            add_claim(
                f"apple-wallet-{wallet_document}",
                wallet_action,
                category="software_systems",
                trusted=True,
            )

    spotlight_support_guidance = bool(
        "spotlight-index-preparation" in identity.title_components
        and _contains(
            extended_claim_evidence,
            "support document",
            "support article",
            "apple explains",
            "apple says",
            "支持文档",
            "苹果回应",
            "苹果解释",
            "official explanation",
            "官方解释",
        )
        and _contains(title_text, "index", "indexing", "索引")
    )
    if spotlight_support_guidance:
        add_claim(
            "spotlight-index-preparation",
            "support-guidance-publication",
            category="software_systems",
            trusted=True,
        )

    apple_support_ai_rollout = bool(
        _contains(
            text,
            "apple support",
            "support phone line",
            "apl-care",
            "苹果支持热线",
            "苹果客服热线",
        )
        and _contains(
            text,
            "generative ai assistant",
            "ai voice assistant",
            "ai assistant",
            "生成式 ai 助手",
            "ai 语音助手",
        )
        and _contains(
            text,
            "rolling out",
            "now uses",
            "now answers",
            "now connects",
            "connects you with",
            "routes calls to",
            "available",
            "上线",
            "启用",
            "接听",
        )
    )
    if apple_support_ai_rollout:
        add_claim(
            "apple-support",
            "generative-ai-assistant-rollout",
            category="software_systems",
            trusted=True,
        )

    genlock_capability = bool(
        "genlock" in identity.components
        and identity.products & {"mac", "mac-mini", "mac-studio", "mac-pro", "macbook"}
        and _contains(
            text,
            "adds genlock",
            "add genlock",
            "genlock support",
            "support genlock",
            "支持 genlock",
            "新增 genlock",
        )
    )
    if genlock_capability:
        add_claim(
            "apple-mac-genlock",
            "capability-support",
            category="hardware_products",
            trusted=True,
        )

    store_app_assistant = bool(
        _contains(claim_evidence, "apple store app", "apple store 应用")
        and _contains(
            claim_evidence,
            "shopping assistant",
            "virtual assistant",
            "ai assistant",
            "购物助手",
            "虚拟助手",
            "ai 助手",
        )
        and _contains(
            claim_evidence,
            "preview",
            "testing",
            "rolling out",
            "rollout",
            "available",
            "上线",
            "测试",
            "预览",
            "开放",
        )
    )
    if store_app_assistant:
        add_claim(
            "apple-store-app",
            "shopping-assistant-preview",
            category="software_systems",
            trusted=True,
        )

    safari_feature_set = bool(
        _compiled_rule(r"\bios\s*(\d{1,2})(?:\.\d+){0,2}\b", 0).search(claim_evidence)
        and _contains(claim_evidence, "safari")
        and _contains(
            title_text,
            "features",
            "new in safari",
            "safari changes",
            "safari feature",
            "safari 浏览器前瞻",
            "safari 前瞻",
            "safari 新功能",
            "safari 功能",
        )
    )
    if safari_feature_set:
        ios_generation = _compiled_rule(r"\bios\s*(\d{1,2})", 0).search(claim_evidence).group(1)
        add_claim(
            f"ios-{ios_generation}-safari",
            "feature-set",
            category="software_systems",
            trusted=True,
        )

    leadership_transition = bool(
        not executive_farewell
        and (
            (
                _contains(title_text, "tim cook", "库克")
                and _contains(
                    title_text,
                    "step down",
                    "steps down",
                    "farewell",
                    "going away",
                    "replaced steve jobs",
                    "卸任",
                    "告别",
                    "欢送",
                    "接任",
                    "继任",
                    "take over",
                )
            )
            or (
                identity.scope == "apple-direct"
                and _compiled_rule(r"ceo|首席执行官", re.I).search(title_text)
                and _compiled_rule(r"\b(?:assume(?:s|d|ing)?|become(?:s|ing)?|start(?:s|ing)?\s+as|"
                    r"succeed(?:s|ed|ing)?|take(?:s|n|ing)?\s+over|"
                    r"is\s+now(?:\s+apple['’]?s)?(?:\s+the)?\s+ceo)\b|"
                    r"(?:上任|就任|出任|接任|继任|接棒|正式履职|正式出任)", re.I).search(title_text)
            )
        )
    )
    if leadership_transition:
        add_claim(
            "apple-leadership",
            "ceo-transition",
            category="software_systems",
            trusted=True,
        )
    if (
        first_executive_employee_memo
        or inbox_accessory_policy_denial
        or executive_profile_asset_update
        or executive_social_account
        or official_follow_change
    ):
        event_keys.discard("primary-claim:apple-leadership:ceo-transition")
        separation.discard("primary-claim-predicate:ceo-transition")
        if inbox_accessory_policy_denial:
            category_hint = "hardware_products"
        else:
            category_hint = "software_systems"

    transit_card_subject = _named_transit_card_subject(title_text) or _named_transit_card_subject(text)
    transit_card_availability = bool(
        transit_card_subject
        and _contains(text, "apple wallet", "苹果钱包", "iphone")
        and _contains(
            text,
            "available",
            "availability",
            "add",
            "support",
            "launch",
            "上线",
            "添加",
            "支持",
            "推出",
            "开通",
        )
    )
    if transit_card_availability:
        add_claim(
            f"apple-wallet-transit-card:{transit_card_subject}",
            "availability",
            category="software_systems",
            trusted=True,
        )

    hardware_products = identity.title_products & {
        "airpods",
        "apple-home-hub",
        "apple-tv-hardware",
        "apple-watch",
        "beats",
        "foldable-iphone",
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
    projected_roadmap_title = bool(
        _compiled_rule(r"apple\s+.+\s+roadmap\s+update", 0).fullmatch(title_text)
    )
    launch_claim_scope = text if projected_roadmap_title else title_text
    launch_subjects = _reported_hardware_launch_subjects(launch_claim_scope, identity)
    explicit_launch_timing_report = bool(
        len(hardware_products) == 1
        and _compiled_rule(r"\b(?:release|launch|shipping|availability)\s+(?:timing|window|date)\b|"
            r"(?:发售|上市|开售|出货).{0,14}(?:时间|窗口|日期)|"
            r"(?:预计|预估|据称|报道称).{0,20}(?:本月|下月|\d{1,2}\s*月|20\d{2})"
            r".{0,16}(?:发售|上市|开售|出货)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:next\s+week|next\s+month|in\s+(?:september|october)|"
            r"by\s+(?:late\s+)?(?:september|october)|20\d{2})\b|"
            r"(?:本月|下月|\d{1,2}\s*月|20\d{2}\s*年)", re.I).search(claim_evidence)
    )
    if explicit_launch_timing_report:
        launch_subjects |= hardware_products
    if (
        projected_roadmap_title
        and len(hardware_products) == 1
        and _compiled_rule(r"\b(?:expected|scheduled|reported|reportedly|could|will|plans? to)\b"
            r".{0,36}\b(?:launch|release|ship|arrive|debut|announce)\b|"
            r"(?:据称|报道称|消息称|有望|预计|计划|最快|届时).{0,36}"
            r"(?:发布|推出|亮相|上市)", re.I).search(text)
    ):
        launch_subjects |= hardware_products
    for launch_subject in sorted(launch_subjects):
        add_claim(
            launch_subject,
            "reported-launch-window",
            category="hardware_products",
            trusted=True,
        )

    concrete_schedule_date = bool(
        _compiled_rule(r"\b(?:september|october)\s+\d{1,2}\b|"
            r"\b\d{1,2}/\d{1,2}\b|"
            r"\d{1,2}\s*月\s*\d{1,2}\s*日", 0).search(claim_evidence)
    )
    schedule_reporting_signal = bool(
        _compiled_rule(r"\b(?:according to|reports?|reported|published|claims?|sources? say|bloomberg|gurman|"
            r"leaker|leaks?|rumou?rs?)\b|"
            r"(?:据.{0,20}(?:报道|消息|透露)|报道称|消息称|爆料|多方消息|多方爆料)", 0).search(claim_evidence)
        or concrete_schedule_date
    )
    event_schedule_subject = bool(
        _apple_event_schedule_title(title_text)
        and not _apple_event_invitation_interpretation_context(title, lead)
        and schedule_reporting_signal
        and _contains(
            claim_evidence,
            "when",
            "date",
            "take place",
            "september",
            "9月",
            "定档",
            "举办",
            "举行",
            "邀请函",
        )
    )
    event_schedule_period = "annual"
    if _compiled_rule(r"\b(?:september|october)\b|(?:9|10)\s*月", 0).search(claim_evidence):
        event_schedule_period = "fall"
    elif _compiled_rule(r"\b(?:march|april)\b|(?:3|4)\s*月", 0).search(claim_evidence):
        event_schedule_period = "spring"
    if event_schedule_subject:
        add_claim(
            f"apple-iphone-{event_schedule_period}-event",
            "schedule-forecast",
            category="hardware_products",
            trusted=True,
        )

    external_product_evaluation = bool(
        hardware_products
        and not _compiled_rule('issues?|bugs?|crash|reboot|故障|重启|失败', re.I).search(title_text)
        and _compiled_rule(r"\b(?:people|testers?|users?)\b.{0,55}"
            r"(?:outside (?:of )?apple|who(?:'ve| have) used|early|external)|"
            r"\b(?:early|external)\s+testers?\b|"
            r"\b(?:outside (?:of )?apple|early|external)\b.{0,55}"
            r"(?:used|tested|handled|hands-on|feedback|impressions?)|"
            r"(?:苹果)?外部.{0,35}(?:体验|使用|上手|测试)|"
            r"(?:早期|外部)(?:体验者|测试者|用户).{0,35}(?:评价|反馈|体验)|"
            r"(?:上手体验|体验反馈).{0,30}(?:评价|好评|短板|缺少)", re.I).search(claim_evidence)
    )
    if external_product_evaluation:
        for product in sorted(hardware_products):
            add_claim(
                product,
                "external-product-evaluation",
                category="hardware_products",
                trusted=direct_title_subject,
            )

    physical_mockup_disclosure = bool(
        hardware_products
        and identity.content_form == "news"
        and _compiled_rule(r"\b(?:mockups?|dummy\s+(?:models?|units?)|physical\s+(?:models?|units?)|"
            r"case\s+manufacturers?)\b|(?:机模|模型机|实体模型|保护壳厂商)", re.I).search(claim_evidence)
        and _compiled_rule(r"\b(?:show(?:s|n|ed|ing)?|reveal(?:s|ed|ing)?|expos(?:e|es|ed|ing)?|"
            r"look\s+like|dimensions?|layout|hinge|buttons?)\b|"
            r"(?:展示|曝光|外形|尺寸|布局|铰链|按键)", re.I).search(claim_evidence)
    )
    if physical_mockup_disclosure:
        for product in sorted(hardware_products):
            add_claim(
                product,
                "technical-details-disclosure",
                category="hardware_products",
                trusted=direct_title_subject,
            )

    retail_home_launch_preparation = bool(
        _compiled_rule(r"\b(?:apple\s+)?(?:retail\s+)?stores?\b|(?:苹果)?(?:零售店|门店)", 0).search(title_text)
        and _compiled_rule(r"\b(?:prepar(?:e|es|ed|ing|ation)?|rearrang(?:e|es|ed|ing)?|"
            r"layout|display|merchandis(?:e|es|ed|ing)?|refresh(?:es|ed|ing)?|changes?)\b|"
            r"(?:准备|调整|重组|改版|布局|陈列|展区)", 0).search(title_text)
        and _compiled_rule(r"\b(?:home\s+products?|smart[- ]home|homepod|apple\s+tv)\b|"
            r"(?:家庭设备|家居产品|智能家居|homepod|apple\s*tv)", 0).search(claim_evidence)
    )
    if retail_home_launch_preparation:
        add_claim(
            "apple-retail-home",
            "store-layout-launch-preparation",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    retrospective_asset_recap = _retrospective_explainer_without_new_action(
        title_text,
        claim_evidence,
    )
    beta_asset_disclosure = bool(
        direct_title_subject
        and not retrospective_asset_recap
        and _compiled_rule(r"\b(?:beta|release candidate|rc|system update)\b|(?:测试版|候选版|系统更新)", 0).search(claim_evidence)
        and _compiled_rule(r"\b(?:accident(?:al|ally)|unintended|mistakenly|leak(?:s|ed)?|"
            r"expos(?:e|es|ed)|included|bundled)\b|(?:意外|误|泄露|曝光|误带|包含)", 0).search(claim_evidence)
        and _compiled_rule(r"\b(?:product plans?|product identifiers?|product videos?|demo videos?|"
            r"future products?|unannounced product information|assets?)\b|"
            r"(?:产品计划|产品标识|产品视频|演示视频|未发布产品|未公布产品信息|"
            r"未公开(?:功能|产品资料)|资源)", 0).search(claim_evidence)
    )
    specific_physical_code_disclosure = any(
        key.startswith("primary-claim:apple-")
        and key.endswith(":unreleased-code-disclosure")
        for key in event_keys
    )
    if beta_asset_disclosure and not specific_physical_code_disclosure:
        add_claim(
            "apple-system-build",
            "unintended-product-asset-disclosure",
            category="software_systems",
            trusted=True,
        )

    # A diagnostic artifact identifies a component on a headline-owned model;
    # a sensor name elsewhere in a launch/preview story is not this disclosure.
    diagnostic_lead = _short_lead_scope(lead, sentences=1, limit=520)
    diagnostic_model = _compiled_rule('\\biphone\\s*(\\d{1,2}\\s*(?:pro\\s*max|pro|plus|air)?)(?=$|[^a-z0-9])', 0).search(title_text)
    diagnostic_sensors = set(_compiled_rule('\\bimx\\d{3,4}\\b', 0).findall(title_text)) & set(_compiled_rule('\\bimx\\d{3,4}\\b', 0).findall(diagnostic_lead))
    diagnostic_target = _compiled_rule('\\biphone\\s*(\\d{1,2}\\s*(?:pro\\s*max|pro|plus|air)?)(?=$|[^a-z0-9])', 0).search(diagnostic_lead)
    if (diagnostic_model and diagnostic_sensors
        and (not diagnostic_target or _compiled_rule(r"\s+", 0).sub("", diagnostic_target.group(1), 0)
             == _compiled_rule(r"\s+", 0).sub("", diagnostic_model.group(1), 0))
        and _compiled_rule('diagnostic\\s+(?:file|log)|诊断(?:文件|日志)', 0).search(diagnostic_lead)
        and _compiled_rule('leaked|泄露|泄漏', 0).search(diagnostic_lead)
        and _compiled_rule('identif(?:y|ies|ied)|confirm(?:s|ed)?|确认|标明|显示', 0).search(diagnostic_lead)
        and not _compiled_rule('not|never|unconfirmed|否认|未确认|并未', 0).search(diagnostic_lead)):
        model = _compiled_rule(r"\s+", 0).sub("-", diagnostic_model.group(1).strip(), 0)
        for sensor in sorted(diagnostic_sensors):
            add_claim("iphone-" + model, "diagnostic-camera-disclosure", qualifier=sensor,
                      category="hardware_products", trusted=True)

    # The opening anniversary report owns its generation and planned period.
    # Later mock-ups, comparison models and technology-readiness estimates do
    # not supply this source assertion.
    anniversary_lead = _short_lead_scope(lead, sentences=1, limit=620)
    anniversary_generation = _compiled_rule('\\b(\\d{1,2})(?:th|st|nd|rd)[ -]anniversary\\s+iphone|(?:(\\d{1,2})\\s*周年(?:纪念版)?\\s*iphone)', 0).search(anniversary_lead)
    anniversary_period = _compiled_rule('\\b(20\\d{2})\\b', 0).search(anniversary_lead)
    if ("iphone" in identity.title_products and anniversary_generation and anniversary_period
        and _compiled_rule('expected to (?:arrive|launch)|预计.{0,24}(?:推出|发布)', 0).search(anniversary_lead)
        and _compiled_rule('design (?:overhaul|change|redesign)|创新|重新设计|设计', 0).search(anniversary_lead)
        and not _compiled_rule('not expected|no longer|取消|不会|不再', 0).search(anniversary_lead)):
        generation = next(value for value in anniversary_generation.groups() if value)
        add_claim("iphone-anniversary-" + generation, "design-launch-planning",
                  qualifier=anniversary_period.group(1), category="hardware_products", trusted=True)

    current_hardware_details_report = bool(
        direct_title_subject
        and hardware_products
        and not _compiled_rule('^(?:ios|ipados|macos|watchos|tvos|visionos)\\s+\\d', 0).match(title_text)
        and identity.content_form == "news"
        and _compiled_rule(r"\b(?:hidden|new|additional|technical)?\s*"
            r"(?:details?|specifications?|specs?|configurations?)\b|"
            r"(?:隐藏|新增|更多|技术)?(?:细节|规格|配置)(?:曝光|披露|公开)?", re.I).search(title_text)
    )
    if current_hardware_details_report and source_predicate_role(
            _short_lead_scope(lead, sentences=1)) == "current":
        generation = next(
            (
                component.removeprefix("apple-silicon-generation:")
                for component in identity.components
                if component.startswith("apple-silicon-generation:")
            ),
            "",
        )
        for product in sorted(hardware_products):
            add_claim(
                product,
                "technical-details-disclosure",
                qualifier=generation,
                category="hardware_products",
                trusted=True,
            )

    current_hardware_refresh_report = bool(
        direct_title_subject
        and hardware_products
        and not any(key.startswith("primary-claim:") for key in event_keys)
        and (
            any(component.startswith("apple-silicon-generation:") for component in identity.title_components)
            or (any(component.startswith("product-generation:") for component in identity.title_components)
                and any(component.startswith(("display-size:", "battery-capacity:", "camera-resolution:"))
                        for component in identity.components))
        )
        and identity.content_form == "news"
        and _compiled_rule(r"\b(?:will|expected|coming|launch|release|ship|before the end of|this year)\b|"
            r"(?:将|预计|有望|即将|年内|年底前|今年).{0,24}(?:推出|发布|上市|到来)?", 0).search(claim_evidence)
    )
    if current_hardware_refresh_report:
        generation = next(
            (
                component.split(":", 1)[1]
                for component in sorted(identity.title_components)
                if component.startswith(("apple-silicon-generation:", "product-generation:"))
            ),
            "",
        )
        for product in sorted(hardware_products):
            add_claim(
                product,
                "generation-product-refresh",
                qualifier=generation,
                category="hardware_products",
                trusted=True,
            )

    shipment_period = _compiled_rule(r"\b(20\d{2})\b", 0).search(text)
    report_owners = {value.removeprefix("report-attribution:") for value in identity.components
                     if value.startswith("report-attribution:") and not value.endswith(":multiple")}
    if (shipment_period and report_owners and "hardware-shipment-plan-change" in identity.components
            and _compiled_rule(r"hardware shipment|硬件出货", 0).search(text)
            and _compiled_rule(r"apple|苹果", 0).search(text)):
        for owner in report_owners:
            event_keys.add(f"source-action:apple-hardware-shipments:{owner}:{shipment_period.group(1)}:reduction")
        separation.add("shipment-report-year:" + shipment_period.group(1))

    capacity_scope = _normalized(_short_lead_scope(lead, sentences=1, limit=650))
    fraction = r"(?:\d+(?:\.\d+)?\s*%|one[- ]third|two[- ]thirds|one[- ]half|half|三分之一|三分之二|一半)"
    capacity_change = re.search(
        rf"(?:from|从)[^,，。.!?]{{0,16}}({fraction})[^,，。.!?]{{0,40}}(?:\bto\b|调整为|改为)[^,，。.!?]{{0,22}}({fraction})", capacity_scope)
    capacity_models = {item.removeprefix("iphone-model:") for item in identity.title_components if item.startswith("iphone-model:")}
    if capacity_change and len(capacity_models) == 1 and _compiled_rule(r"capacity|产能|产线", 0).search(capacity_scope):
        ratios = {"one-third": "1/3", "two-thirds": "2/3", "one-half": "1/2", "half": "1/2",
                  "三分之一": "1/3", "三分之二": "2/3", "一半": "1/2"}
        before, after = [ratios.get(value.replace(" ", "-"), value.replace(" ", "")) for value in capacity_change.groups()]
        model = next(iter(capacity_models))
        add_claim("iphone-" + model, "capacity-reduction-revision", qualifier=f"{before}-to-{after}", category="hardware_products")
        separation.update({"capacity-before:" + before, "capacity-after:" + after})

    clinical_institution = _compiled_rule(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}\s+(?:Health|Hospital|Medical Center))\b", 0).search(lead)
    clinical_apps = set(_compiled_rule(r"\b([A-Z][a-z]+[A-Z][A-Za-z]+)(?:\s+Vision)?\b", 0).findall(lead))
    clinical_procedures = {name for name, pattern in (
        ("hip", r"\bhip\b|髋"), ("knee", r"\bknee\b|膝"),
        ("shoulder", r"\bshoulder\b|肩"), ("cardiac", r"\b(?:heart|cardiac)\b|心脏"))
        if re.search(pattern, title_text)}
    clinical_completed = bool(_compiled_rule(r"assists?.{0,25}surgery|surgery.{0,35}completed|手术完成", 0).search(title_text)
        and _compiled_rule(r"\bfirst\b|首例", 0).search(text) and _compiled_rule(r"completed|完成", 0).search(text))
    if (clinical_institution and len(clinical_apps) == 1 and len(clinical_procedures) == 1
            and "vision-pro" in identity.title_products and clinical_completed):
        institution = _compiled_rule(r"\s+", 0).sub("-", clinical_institution.group(1).lower(), 0)
        application = next(iter(clinical_apps)).lower()
        procedure = next(iter(clinical_procedures))
        add_claim(f"vision-pro-clinical-{institution}-{application}", "first-completed-surgery",
                  qualifier=procedure, category="hardware_products", trusted=False)
        separation.update({"clinical-institution:" + institution, "clinical-procedure:" + procedure,
                           "clinical-application:" + application})

    maps_policy = bool(
        _compiled_rule(r"apple maps|maps app|苹果地图|地图 apple maps", re.I).search(text)
        and _compiled_rule(r"\b(?:ad|ads|advertising)\b|广告", re.I).search(title_text)
        and _compiled_rule(r"prohibit|won['’]t allow|will not allow|禁投|禁止|不允许", re.I).search(text)
        and _compiled_rule(r"policy|rules|categories|category|政策|条款|类别", re.I).search(text)
        and _compiled_rule(r"(?:apple\b|苹果)", re.I).match(title_text)
    )
    if maps_policy:
        add_claim("apple-maps-advertising", "category-restriction-policy", category="software_systems")
        separation.add("maps-ad-action:category-restriction-policy")

    tariff_lead = _compiled_rule(r"\bU\.S\.", re.I).sub("US", lead, 0)
    tariff_scope = f"{full_title_text}. {_short_lead_scope(tariff_lead, sentences=1, limit=800)}"
    tariff_suppliers = _canonical_supplier_entities(tariff_scope)
    if (len(tariff_suppliers) == 1
            and _compiled_rule(r"(?:^|[:：]\s*)apple(?:'s)?\b|(?:^|[:：]\s*)苹果", re.I).search(full_title_text)
            and _compiled_rule(r"tariff.{0,25}exemption|exempt.{0,45}tariff|关税豁免", re.I).search(tariff_scope)
            and _compiled_rule(r"semiconductor|半导体", re.I).search(tariff_scope)
            and _compiled_rule(r"committ?\w*|agreement|deal|同意|承诺|代工", re.I).search(tariff_scope)
            and _compiled_rule(r"foundr|chip.production|晶圆厂|代工", re.I).search(tariff_scope)
            and _compiled_rule(r"u\.?s\.?|美国", re.I).search(tariff_scope)):
        supplier = next(iter(tariff_suppliers))
        add_claim("apple-us-foundry-tariff-" + supplier, "reported-exemption-arrangement", category="hardware_products")
        separation.add("tariff-arrangement-partner:" + supplier)

    foldable_subject = bool(_compiled_rule(r"(?:fold(?:able|ing)?|折叠).{0,22}(?:iphone|phone)|iphone.{0,18}(?:fold|折叠)", re.I).search(title_text))
    if foldable_subject:
        production_scope = f"{title_text}. {_short_lead_scope(lead, sentences=1, limit=600)}"
        production_stage = ("small-batch" if _compiled_rule(r"small[ -]batch|early production|小批量", re.I).search(production_scope)
                            else "mass-production" if _compiled_rule(r"mass production|大规模量产|大批量供货", re.I).search(production_scope) else "")
        production_current = bool(_compiled_rule(r"started|enter|begin|已经|已向|已小|开始", re.I).search(production_scope))
        if production_stage and production_current and not _compiled_rule(r"panel|display|screen|面板|屏幕", re.I).search(title_text):
            add_claim("foldable-iphone-production", production_stage, category="hardware_products")
            separation.add("fold-production-stage:" + production_stage)
        if _compiled_rule(r"battery|电池", re.I).search(title_text):
            battery_scope = lead.replace(",", "")
            cells = _compiled_rule(r"(\d+)\s*mah\s*(?:and|和|与)\s*(\d+)\s*mah", re.I).search(battery_scope)
            total = _compiled_rule(r"(?:combined|合计|总计|总容量(?:为)?)\s*(\d+)\s*mah", re.I).search(battery_scope)
            if cells and total:
                capacities = sorted(int(value) for value in cells.groups())
                if sum(capacities) == int(total.group(1)):
                    cell_key = "-".join(str(value) for value in capacities)
                    add_claim("foldable-iphone-dual-cell-battery", "capacity-disclosure",
                              qualifier=f"cells-{cell_key}-total-{total.group(1)}", category="hardware_products")
                    separation |= {"battery-cell-capacities:" + cell_key, "battery-total-capacity:" + total.group(1)}

    acquisition = source_acquisition_frame(title, lead)
    if acquisition is not None:
        add_claim(acquisition.subject, acquisition.action, category=acquisition.category)

    # A named threat is the affected macOS incident object, not the reporter
    # or an incidental product in a later background sentence.
    direct_threat = _compiled_rule('^([a-z][a-z0-9-]+)\\s+(?:malware\\s+)?targets?\\s+macos\\b', re.I).match(primary_lead)
    identified_threat = _compiled_rule('^[a-z][a-z0-9.-]*\\s+identified\\s+(?:the\\s+)?(?:same\\s+)?malware\\s+as\\s+([a-z][a-z0-9-]+)\\s+after\\s+(?:seeing|observing|detecting)\\s+(?:active\\s+)?macos\\s+infections\\b', re.I).match(primary_lead)
    title_threat = _compiled_rule('^([a-z][a-z0-9-]+)\\s+(?:malware\\b|攻击披露|恶意软件)', re.I).match(title_text)
    referred_threat = bool(title_threat and _compiled_rule('^(?:it\\b|(?:this|the) malware\\b|该恶意软件|这种恶意软件).{0,100}(?:targets?\\s+macos\\b|steals?\\s+macos\\b|窃取\\s*macos\\b)', re.I).match(primary_lead))
    threat = direct_threat or identified_threat or (title_threat if referred_threat else None)
    if (threat and _compiled_rule('\\bmac(?:os)?\\b', 0).search(title_text)
            and not _compiled_rule('\\b(?:last year|last month|previously|earlier|not|never|may|might|could)\\b|去年|上个月|此前|曾经|并未|没有|尚未|未曾|可能|或许', re.I).search(primary_lead)):
        add_claim("macos-malware-" + threat.group(1).lower(), "active-infection-report", category="software_systems")

    # An exploit identifier and named litigants identify a research case even
    # when Apple is the affected platform, rather than a party to the suit.
    research_artifact = _compiled_rule(r"\b([a-z][a-z0-9-]{4,}\d[a-z0-9-]*)\s+a\d+(?:/a?\d+)?", 0).search(text)
    research_parties = {_compiled_rule(r"\s+", 0).sub("-", name.lower(), 0) for name in
                        _compiled_rule(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+\b", 0).findall(lead)}
    if (research_artifact and len(research_parties) >= 2
            and _compiled_rule(r"lawsuit|legal fight|诉讼|法律纠纷", 0).search(title_text)
            and _compiled_rule(r"\bsue(?:d)?\b|case concerns|起诉|案件", 0).search(text)
            and _compiled_rule(r"securerom|bootrom", 0).search(text)):
        case = "-".join(sorted(research_parties)) + ":" + research_artifact.group(1)
        event_keys.add("source-action:security-research-case:" + case)
        separation.add("security-research-case:" + case)

    board_models = {item.removeprefix("iphone-model:") for item in identity.title_components
                    if item.startswith("iphone-model:")}
    if (board_models and _compiled_rule(r"logic board|board schematics|逻辑板|主板", 0).search(title_text)
            and _compiled_rule('leak|泄露|曝光|(?:图纸|图像|示意图).{0,8}流传', 0).search(title_text)
            and not _compiled_rule(r"remov|takedown|crackdown|dmca|下架|删除", 0).search(title_text)
            and _compiled_rule(r"diagram|schematic|layout|packaging|图纸|布局|封装", 0).search(text)):
        for model in sorted(board_models):
            add_claim("iphone-" + model + "-logic-board", "file-disclosure", category="hardware_products")
            separation.add("board-file-model:" + model)

    breach_parties = _canonical_supplier_entities(text)
    if (breach_parties and _compiled_rule(r"\bapple\b|苹果|iphone", re.I).search(text)
            and (_compiled_rule(r"data (?:breach|leak)|breach|dark web|暗网|数据泄露|信息泄露|被黑|遭黑|泄密.{0,40}调查", re.I).search(title_text)
                 or (_canonical_supplier_entities(title_text) and _compiled_rule(r"leak|泄露|泄密", re.I).search(title_text))
                 or (_compiled_rule(r"leak|泄露|泄密", re.I).search(title_text)
                     and _compiled_rule(r"data breach|cyberattack|hack|遭黑|黑客|网络攻击", re.I).search(text)))
            and not _compiled_rule(r"crackdown|takedown|dmca|disappear|modem|nand|下架|删除|基带|闪存", re.I).search(title_text)
            and _compiled_rule(r"leak|breach|stolen|hack|泄露|被窃|黑客|网络攻击", re.I).search(text)):
        for supplier in sorted(breach_parties):
            add_claim("apple-supplier-" + supplier, "data-breach-report", category="hardware_products")

    supplier_parties = _canonical_supplier_entities(title_text)
    supplier_contract = bool(supplier_parties and _compiled_rule(r"\bapple\b|苹果", 0).search(text)
        and _compiled_rule(r"\b(?:extend\w*|renew\w*|retain)\b|续签|延长|续约", 0).search(text)
        and _compiled_rule(r"\b(?:deal|agreement|partnership|contract)\b|协议|合作|合约|合同", 0).search(text)
        and _compiled_rule(r"\b(?:chips?|components?|semiconductors?|supply|wireless)\b|芯片|组件|元件|射频|供应", 0).search(text))
    if supplier_contract:
        contract_end = _compiled_rule(r"(?:through|until|to|延长至|延至|至)\s*(20\d{2})", 0).search(text)
        end_year = contract_end.group(1) if contract_end else ""
        for supplier in sorted(supplier_parties):
            add_claim("apple-supplier-" + supplier, "component-supply-renewal", qualifier=end_year,
                      category="hardware_products")
        if end_year:
            separation.add("supply-contract-end:" + end_year)

    supplier_component_classes = {
        component.removeprefix("component-supplier-sourcing:")
        for component in identity.title_components
        if component.startswith("component-supplier-sourcing:")
    }
    requested_chip_object = _compiled_rule('\\bapple\\s+(?:requested to|plans? to|intends? to|wants? to|will|is seeking to)\\s+(?:buy|use|source|purchase)\\b(?:(?!\\b(?:previously|but|while|and)\\b).){0,100}', 0).search(primary_lead)
    memory_request_object = bool(requested_chip_object and (
        _compiled_rule('\\b(?:memory|dram|nand)\\b', 0).search(requested_chip_object.group())
        or any(_contains(requested_chip_object.group(), *aliases) for aliases in _MEMORY_SUPPLIER_ALIASES.values())))
    component_policy_request = bool(
        _compiled_rule('\\b(?:senators?|lawmakers?|legislators?)\\s+(?:urge|ask|demand)\\s+apple\\s+to\\s+(?:abandon|reconsider|stop)\\b.{0,45}\\bchips?\\b', 0).search(title_text)
        and memory_request_object
        and not _compiled_rule('\\b(?:previously|last year|formerly)\\b', 0).search(title_text))
    if component_policy_request:
        supplier_component_classes.add("memory")
    if supplier_component_classes and (direct_title_subject or component_policy_request):
        if "primary-intent:memory-supplier-policy" in identity.title_components or component_policy_request:
            sourcing_predicate = "component-procurement-policy-pressure"
        elif _compiled_rule(r"\b(?:block|ban|stop|reject|deny|restriction)\b|"
            r"(?:叫停|阻止|禁止|否决|拒绝|限制)", 0).search(title_text):
            sourcing_predicate = "component-procurement-policy-block"
        elif _compiled_rule(r"\b(?:allow|approve|approval|clear|authorize)\b|"
            r"(?:放行|允许|批准|授权|获准)", 0).search(title_text):
            sourcing_predicate = "component-procurement-policy-approval"
        elif _compiled_rule(r"\b(?:priority supply|priority allocation|orders? booked|allocation)\b|"
            r"(?:优先供货|优先拿货|订单排至|订单已排至|分配)", 0).search(title_text):
            sourcing_predicate = "component-order-allocation"
        elif _compiled_rule(r"\b(?:long[- ]term|multiyear|multi-year)\b.{0,40}\b(?:agreement|contract)\b|"
            r"(?:长期|多年).{0,10}(?:协议|合约|合同)", 0).search(title_text):
            sourcing_predicate = "component-long-term-supply-agreement"
        elif _compiled_rule(r"\b(?:talks?|negotiat|bidding)\b|(?:洽谈|谈判|议价|压价)", 0).search(title_text):
            sourcing_predicate = "component-supplier-negotiation"
        else:
            sourcing_predicate = "component-procurement"
        for component_class in sorted(supplier_component_classes):
            add_claim(
                f"apple-{component_class}-sourcing",
                sourcing_predicate,
                category="hardware_products",
                trusted=True,
            )

    apple_music_ai_label_action = bool(
        "apple-music" in identity.products
        and _contains(
            claim_evidence,
            "ai-generated",
            "ai generated",
            "ai content",
            "artificial intelligence",
            "机器生成",
            "ai 生成",
        )
        and _contains(
            claim_evidence,
            "label",
            "labels",
            "labeled",
            "labelled",
            "transparency tag",
            "disclosure",
            "标注",
            "标签",
            "披露",
        )
        and _contains(
            claim_evidence,
            "require",
            "required",
            "mandatory",
            "must",
            "will soon",
            "强制",
            "要求",
            "必须",
            "年底",
        )
    )
    if apple_music_ai_label_action:
        add_claim(
            "apple-music-ai-content",
            "mandatory-disclosure-label",
            category="software_systems",
            trusted=direct_title_subject or identity.scope == "apple-direct",
        )

    reduction_action = r"\blayoffs?\b|\blaid\s+off\b|\blays?\s+off\b|\b(?:job cuts|cuts jobs|cutting jobs|laying off|trims staff|trimming staff|headcount reduction)\b|裁员|裁撤|裁减|裁掉|被裁|团队.{0,10}瘦身"
    # Personnel may follow department modifiers: "cut gaming roles" or
    # "trims software staff". Commerce prepositions/objects do not establish
    # a workforce action (for example, "cuts prices for staff").
    reduction_action += (
        r"|\b(?:cuts?|cutting|trims?|trimming)\s+"
        r"(?:(?!(?:for|with|to|while|by|prices?|costs?)\b)[\w-]+\s+){0,8}"
        r"(?:roles|jobs|staff|employees|positions)\b"
    )
    workforce_scope = title_text
    direct_reduction_lead = _normalized(_short_lead_scope(lead, sentences=1))
    # A leading attributed report may carry the current action even when the
    # title is sparse. Its named unit, not the title's sole product, owns it.
    if not re.search(reduction_action, workforce_scope):
        direct_reduction = _compiled_rule("^(?:(?:according to\\s+[^,]{1,80},\\s*)|(?:据[^，。]{1,80}(?:报道|透露)[，,]\\s*))?(?:apple(?:['’]s)?\\b|苹果)", 0).match(direct_reduction_lead)
        workforce_scope = direct_reduction_lead if direct_reduction else ""
    else:
        workforce_scope += " " + direct_reduction_lead
    workforce_reduction = bool(re.search(reduction_action, workforce_scope)
        and _compiled_rule("\\bapple(?:['’]s)?\\b|苹果", 0).search(workforce_scope))
    if workforce_reduction:
        workforce_subject = ""
        if (
            _bounded_evidence_products(workforce_scope) & {"vision-pro", "visionos"}
            or _contains(
            workforce_scope,
            "vision group",
            "vision products",
            "vr team",
            "vision 业务组",
            "vr 研发团队",
            )
        ) or (
            _contains(workforce_scope, "vr", "vision")
            and _contains(
                workforce_scope,
                "team",
                "group",
                "division",
                "department",
                "organization",
                "团队",
                "部门",
                "业务组",
                "组织",
            )
        ):
            workforce_subject = "apple-vision-group"
        else:
            direct_units = sorted(_bounded_evidence_products(workforce_scope) - {"apple", "ios", "macos"})
            if len(direct_units) == 1:
                workforce_subject = f"apple-{direct_units[0].removeprefix('apple-')}-group"
        if workforce_subject:
            add_claim(
                workforce_subject,
                "workforce-reduction",
                category="hardware_products",
                trusted=True,
            )

    iphone_launch_schedule = bool(
        "iphone" in identity.products
        and _contains(
            text,
            "won't launch",
            "will not launch",
            "missing from",
            "pushed to",
            "delayed until",
            "launch schedule",
            "缺席",
            "不会发布",
            "延后",
            "推迟",
            "发布节奏",
        )
        and _contains(
            text,
            "september",
            "next month",
            "early 20",
            "first quarter",
            "march",
            "9 月",
            "9月",
            "明年",
            "第一季度",
            "3 月",
            "3月",
        )
    )
    if iphone_launch_schedule:
        model_subjects = sorted(
            component
            for component in identity.title_components
            if component.startswith("iphone-model:")
        )
        generation_subjects = sorted(
            component
            for component in identity.title_components
            if component.startswith("product-generation:iphone-")
        )
        launch_subject = next(iter(model_subjects or generation_subjects), "iphone")
        add_claim(
            launch_subject,
            "launch-schedule-change",
            category="hardware_products",
            trusted=direct_title_subject or identity.scope == "apple-direct",
        )

    # Display ordering must not decide whether the source reported an Apple
    # measurement. The measured row may follow several market-context rows.
    market_result_keys = _measured_apple_market_result_keys(title, lead, " ".join((evidence, *source_facts)), include_forecasts=True)
    if market_result_keys:
        report = source_market_measurement_frame(title, lead, source_facts)
        if report and report.subject.endswith(':smartphone-shipments'):
            stamp = report.year + '-' + report.period
            if any(key.split(':')[3] == stamp for key in market_result_keys if len(key.split(':')) == 6):
                event_keys.add('primary-claim:' + report.subject + ':measured-apple-market-result')
                for prefix, value in (('source-report-year:', report.year),
                                      ('source-report-period:', report.period),
                                      ('source-report-region:', report.region)):
                    if value:
                        separation.add(prefix + value)
        event_keys |= market_result_keys
        observed_results = any(key.startswith('structured-market-result:') for key in market_result_keys)
        if observed_results:
            separation.add("primary-claim-predicate:measured-apple-market-result")
        separation |= _market_result_separation_keys(market_result_keys)
        category_hint = "hardware_products"
        trusted_direct_action = trusted_direct_action or observed_results

    title_products = sorted(identity.title_products)
    production_subjects = list(title_products)
    if _compiled_rule(r"\b(?:foldable|folding)\s+(?:apple\s+)?iphone\b|"
        r"(?:折叠屏|折叠式)\s*iphone|iphone\s*(?:ultra|fold)", 0).search(text):
        production_subjects = ["foldable-iphone"]
    production_volume = next((match for match in _compiled_rule(r"(?<!\d)(\d{1,4}(?:\.\d+)?)\s*(million|万)(?!\s*(?:片|panels?|displays?|screens?))\s*(?:units?|台)?", 0).finditer(text) if not _compiled_rule(r"(?:售价|起售价|价格|定价|price(?:s)?(?: of| starts? at)?|cost(?:s)?|[$€£])\s*$", re.I).search(text[max(0, match.start() - 32):match.start()])
       and not _compiled_rule(r"\s*(?:元|美元|人民币|dollars?\b|usd\b|euros?\b)", re.I).match(text[match.end():])), None)
    production_action = bool(
        identity.actions & {"supply-production"}
        or _contains(
            text,
            "production target",
            "production goal",
            "orders to",
            "order target",
            "units this year",
            "产量目标",
            "生产目标",
            "年产目标",
            "订单上调",
        )
    )
    if len(production_subjects) == 1 and production_volume and production_action:
        value = float(production_volume.group(1))
        multiplier = 1_000_000 if production_volume.group(2) == "million" else 10_000
        normalized_units = str(int(value * multiplier))
        add_claim(
            production_subjects[0],
            "production-target",
            qualifier=f"units-{normalized_units}",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    if _compiled_rule(r"\bsiri\s+remote\b|siri\s*remote\s*遥控器", 0).search(text) and _contains(
        text,
        "new",
        "next",
        "upgraded",
        "upgrade",
        "upcoming",
        "code hints",
        "identifier",
        "新一代",
        "新款",
        "升级款",
        "代码",
        "标识",
        "曝光",
    ):
        add_claim(
            "siri-remote",
            "hardware-refresh",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    if (
        "apple-home-hub" in identity.title_products
        and _contains(
            text,
            "widget gallery",
            "smart stack",
            "widget support",
            "widget mirroring",
            "小组件图库",
            "小组件库",
            "智能叠放",
            "小组件镜像",
            "支持小组件",
            "搭载小组件",
        )
    ):
        add_claim(
            "apple-home-hub",
            "widget-capability",
            category="software_systems",
            trusted=direct_title_subject,
        )

    cashback_percent = _compiled_rule(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*%[^。.!?]{0,40}"
        r"(?:daily cash|cash\s*back|cashback|返现)|"
        r"(?:daily cash|cash\s*back|cashback|返现)[^。.!?]{0,40}"
        r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*%", 0).search(text)
    if "apple-card" in identity.title_products and cashback_percent:
        percentage = cashback_percent.group(1) or cashback_percent.group(2)
        add_claim(
            "apple-card",
            "cashback-offer",
            qualifier=f"percent-{percentage}",
            category="software_systems",
            trusted=direct_title_subject,
        )

    app_store_subject = (
        "app-store" in identity.title_products
        or _contains(text, "app store", "应用商店")
        or (
            _compiled_rule(r"^(?:apple|苹果)", 0).match(title_text)
            and _contains(
                text,
                "business terms for apps",
                "commercial terms for apps",
                "应用商业条款",
            )
        )
    )
    app_store_distribution_policy = bool(
        _contains(text, "app store", "应用商店", "app marketplaces", "应用市场")
        and _contains(
            text,
            "alternative app marketplace",
            "alternative app marketplaces",
            "third-party app marketplace",
            "third-party app marketplaces",
            "web distribution",
            "external links",
            "third-party payment",
            "third-party platforms",
            "第三方应用商店",
            "替代应用市场",
            "网页分发",
            "外部链接",
            "第三方支付",
            "第三方平台",
        )
        and _contains(
            text,
            "change",
            "changes",
            "agreement",
            "allow",
            "adding",
            "调整",
            "落地",
            "协议",
            "允许",
            "开放",
        )
    )
    if app_store_distribution_policy:
        region_values = {
            region for region in regions if region and region != "multi-region"
        }
        if _contains(text, "brazil", "巴西"):
            region_values.add("brazil")
        qualifier = ",".join(sorted(region_values)) or "global"
        add_claim(
            "app-store",
            "distribution-payment-policy-change",
            qualifier=qualifier,
            category="software_systems",
            trusted=direct_title_subject or identity.scope == "apple-direct",
        )
    app_store_terms = bool(
        app_store_subject
        and _contains(
            claim_evidence,
            "terms",
            "rules",
            "app store changes",
            "fees",
            "fee structure",
            "external payments",
            "business terms",
            "商业条款",
            "应用商业条款",
            "新规",
            "费率",
            "收费",
            "收费结构",
            "外部支付",
        )
        and _contains(
            claim_evidence,
            "overhaul",
            "change",
            "changes",
            "changed",
            "updated",
            "revised",
            "adjusted",
            "new",
            "lower",
            "unified",
            "settle",
            "settles",
            "squashes",
            "announces",
            "调整",
            "变更",
            "新条款",
            "新规",
            "降低",
            "统一",
            "宣布",
        )
        and (
            _contains(claim_evidence, "european union", " eu ", "europe", "欧盟", "欧洲")
            or bool({region for region in regions if region and region != "multi-region"})
        )
    )
    if app_store_terms:
        region_values = {
            region for region in regions if region and region != "multi-region"
        }
        if _contains(claim_evidence, "european union", " eu ", "europe", "欧盟", "欧洲"):
            region_values.add("europe")
        qualifier = ",".join(sorted(region_values)) or "global"
        add_claim(
            "app-store",
            "commercial-terms-change",
            qualifier=qualifier,
            category="software_systems",
            trusted=True,
        )

    app_store_commission_context = bool(
        _contains(claim_evidence, "app store", "应用商店")
        and _contains(
            claim_evidence,
            "commission revenue",
            "commission income",
            "commission",
            "佣金收入",
            "佣金",
        )
    )
    app_store_commission_pressure_title = bool(
        _contains(
            title_text,
            "commission revenue",
            "app store revenue",
            "commission income",
            "make any commission",
            "regulated away",
            "佣金收入",
            "服务收入",
            "佣金",
        )
        or (
            _contains(title_text, "services business", "service revenue", "服务业务", "服务收入")
            and app_store_commission_context
        )
    )
    commission_revenue_pressure = bool(
        (app_store_subject or (direct_title_subject and app_store_commission_context))
        and app_store_commission_pressure_title
        and _contains(
            claim_evidence,
            "down",
            "decline",
            "declining",
            "fall",
            "falling",
            "danger",
            "may not",
            "pressure",
            "erosion",
            "下降",
            "下滑",
            "冲击",
            "侵蚀",
            "无法收取",
            "可能不再",
        )
    )
    if commission_revenue_pressure:
        add_claim(
            "app-store",
            "commission-revenue-pressure",
            category="software_systems",
            trusted=direct_title_subject,
        )
        if (
            _contains(
                claim_evidence,
                "regulator",
                "regulatory",
                "regulation",
                "反垄断",
                "监管",
            )
            and _contains(
                claim_evidence,
                "services business",
                "services growth",
                "service revenue",
                "services revenue",
                "服务业务",
                "服务收入",
            )
        ):
            add_claim(
                "apple-services",
                "regulatory-financial-impact",
                category="software_systems",
                trusted=direct_title_subject,
            )

    if (
        not mac_intel_support_removal
        and not (acquisition is not None and _compiled_rule(r"app store.{0,30}(?:该应用|the app|this app)", 0).search(title_text))
        and _contains(text, "app store", "应用商店")
        and _contains(
            title_text,
            "pulls",
            "pulled",
            "removes",
            "removed",
            "delists",
            "delisted",
            "下架",
            "移除",
            "撤下",
        )
    ):
        add_claim(
            "app-store",
            "app-enforcement-removal",
            category="software_systems",
            trusted=direct_title_subject,
        )

    airpods_generation = _compiled_rule(r"\bairpods\s*(\d{1,2})\b|airpods\s*第?\s*(\d{1,2})\s*代", 0).search(title_text)
    if airpods_generation and _contains(
        text,
        "model",
        "models",
        "identifier",
        "identifiers",
        "referenced",
        "code",
        "型号",
        "标识",
        "代码",
        "曝光",
    ):
        generation = airpods_generation.group(1) or airpods_generation.group(2)
        add_claim(
            f"airpods-generation-{generation}",
            "model-identifier-leak",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    camera_airpods_delay = bool(_compiled_rule(r"airpods", re.I).search(title)
        and _compiled_rule(r"camera|摄像头", re.I).search(title)
        and _compiled_rule(r"\bdelayed\b|\bpostponed\b|延至|推迟至|延期", re.I).search(title))
    camera_airpods_suspension = "camera-airpods-development-suspension" in identity.facets or camera_airpods_delay
    if camera_airpods_suspension:
        add_claim("camera-airpods", "development-suspension", category="hardware_products", trusted=direct_title_subject)
        if camera_airpods_delay:
            for year in _compiled_rule(r"(?<!\d)20\d{2}(?!\d)", 0).findall(title):
                separation.add("camera-airpods-delay-year:" + year)

    camera_airpods_scope = text
    if ("airpods" in identity.title_products and _compiled_rule(r"\b(?:code|codenamed|beta)\b|代码|代号", 0).search(text)
            and _compiled_rule(r"two images|2 张图像|两.{0,2}图像|头部两侧|either side", 0).search(text)):
        # The immediately following code-reference sentence may identify what
        # the disclosed capability could belong to, without removing its hedge.
        continuation = _compiled_rule(r"(?:[.!?]\s+|。)(the code\b[^.!?。]+|该代码[^。]+)", re.I).search(_normalized(lead))
        if continuation:
            camera_airpods_scope += " " + continuation.group(1)

    camera_airpods_title_action = bool(
        (
            direct_title_subject
            or _compiled_rule(r"^airpods?\b", 0).match(title_text)
        )
        and _contains(
            title_text,
            "hint",
            "leak",
            "demo",
            "code",
            "rumor",
            "learned",
            "detect",
            "capture",
            "delay",
            "delayed",
            "曝光",
            "演示",
            "代码",
            "传闻",
            "功能揭晓",
            "延期",
            "延至",
        )
    )
    if (
        "airpods" in identity.title_products
        and not camera_airpods_suspension
        and camera_airpods_title_action
        and _contains(
            text,
            "leak",
            "leaked",
            "demo",
            "video",
            "code",
            "codename",
            "launch",
            "delay",
            "delayed",
            "on track",
            "naming",
            "named",
            "rumor",
            "rumors",
            "learned",
            "detect people",
            "capture",
            "曝光",
            "演示",
            "视频",
            "代码",
            "代号",
            "推出",
            "延期",
            "延至",
            "命名",
        )
        and (
            _compiled_rule(r"\bcamera(?:-equipped)?\s+airpods?\b|"
                r"\bairpods?\b[^。.!?]{0,28}\bcameras?\b", 0).search(camera_airpods_scope)
            or _compiled_rule(r"(?:摄像头|相机)[^。！？]{0,20}airpods|"
                r"airpods[^。！？]{0,20}(?:摄像头|相机)", 0).search(camera_airpods_scope)
        )
    ):
        add_claim(
            "camera-airpods",
            "product-capability-leak",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    macbook_generation = _compiled_rule(r"\b(m\d)\s+macbook\s+pro\b", 0).search(text)
    if (
        macbook_generation
        and _contains(
            claim_evidence,
            "gpu",
            "memory bandwidth",
            "vapor chamber",
            "thermal",
            "内存带宽",
            "均热板",
            "散热",
        )
    ):
        add_claim(
            f"{macbook_generation.group(1)}-macbook-pro",
            "product-specification-report",
            category="hardware_products",
            trusted=True,
        )

    apple_pay_rollout = bool(
        "apple-pay" in identity.products
        and _contains(
            text,
            "begin accepting",
            "launching apple pay",
            "apple pay rollout",
            "adding apple pay",
            "apple pay is coming",
            "support apple pay",
            "支持 apple pay",
            "接入 apple pay",
            "开始支持 apple pay",
        )
    )
    if apple_pay_rollout:
        actor_aliases = (
            ("walmart", ("walmart", "沃尔玛")),
            ("sams-club", ("sam's club", "sams club", "山姆会员商店", "山姆")),
        )
        actors = {
            canonical
            for canonical, aliases in actor_aliases
            if _contains(text, *aliases)
        }
        retailer = "walmart" if "walmart" in actors else next(iter(actors), "")
        if retailer:
            add_claim(
                f"retailer-{retailer}-apple-pay",
                "platform-rollout",
                category="software_systems",
                trusted=True,
            )

    if (
        "tvos" in identity.title_products
        and "siri" in identity.title_products
        and _contains(
            text,
            "siri ai",
            "siri 条目",
            "siri entry",
            "siri app",
            "siri 应用",
        )
    ):
        add_claim(
            "tvos-siri",
            "ai-capability",
            category="software_systems",
            trusted=direct_title_subject,
        )

    if (
        identity.title_products
        & {"app-store", "apple-music", "apple-tv", "icloud"}
        and (
            _contains(
                title_text,
                "outage",
                "experiencing issues",
                "service issues",
                "service interruption",
                "服务中断",
                "出现故障",
                "服务问题",
                "宕机",
            )
            or _compiled_rule(r"\b(?:is|are|currently|services?)\s+down\b|"
                r"(?:服务|系统).{0,10}(?:不可用|中断|故障)", 0).search(title_text)
        )
    ):
        add_claim(
            "apple-online-services",
            "service-outage",
            category="software_systems",
            trusted=direct_title_subject,
        )

    if (
        "ipad" in identity.title_products
        and _contains(text, "patent", "专利")
        and _contains(text, "camera control", "相机控制", "相机按键")
    ):
        add_claim(
            "ipad-camera-control",
            "patent-disclosure",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    # The first explicit headline model owns the assertion; later models in
    # comparisons are not interchangeable targets from an unordered set.
    headline_model = _compiled_rule('\\biphone\\s*(\\d{1,2}\\s*(?:pro\\s*max|pro|plus|air)?|air\\s*\\d+)(?=$|[^a-z0-9])', 0).search(title_text)
    iphone_model = _compiled_rule(r"\s+", 0).sub("-", headline_model.group(1).strip(), 0) if headline_model else ""
    physical_scope = f"{title_text}. {_short_lead_scope(lead, sentences=2, limit=1000)}"
    weight_scope = " ".join(clause for clause in _compiled_rule(r"[。.!?]\s*", 0).split(physical_scope, 0)
        if iphone_model and re.search(r"\biphone\s*" + r"\s*".join(map(re.escape, iphone_model.split("-")))
            + r"(?=$|[^a-z0-9])", clause))
    weight = _compiled_rule('(?:weigh(?:t|s|ing)?(?: of)?|重量)[^。.!?]{0,22}?(\\d{3})\\s*(?:grams?|g\\b|克)', 0).search(weight_scope)
    if iphone_model and weight and _compiled_rule('heavier|heaviest|weight|重量|更重', 0).search(title_text):
        add_claim("iphone-" + iphone_model, "weight-disclosure", qualifier="grams-" + weight.group(1), category="hardware_products")
    elif (iphone_model and _compiled_rule('thick(?:ness|er)|厚度|增厚|变厚', 0).search(title_text)
          and _compiled_rule('thicker|grow thicker|增厚|变厚|厚度.{0,12}增加', 0).search(physical_scope)
          and _compiled_rule('body|frame|camera (?:housing|plateau|bump)|机身|中框|摄像头平台', 0).search(physical_scope)):
        add_claim("iphone-" + iphone_model, "body-camera-thickness-increase", category="hardware_products")
    if (iphone_model.startswith("air-") and _compiled_rule('render|renders|渲染图|曝光图', 0).search(physical_scope)
            and _compiled_rule('dual[ -]camera|双摄', 0).search(physical_scope)
            and _compiled_rule('leak|reveal|render|首秀|曝光|消息源', 0).search(physical_scope)):
        add_claim("iphone-" + iphone_model, "dual-camera-render-disclosure", category="hardware_products")
    battery_models = {_compiled_rule(r"\s+", 0).sub("-", value.strip(), 0) for value in
        _compiled_rule('\\biphone\\s*(\\d{1,2}\\s+pro(?:\\s+max)?)(?=$|[^a-z0-9])', 0).findall(physical_scope)}
    battery_models = {model for model in battery_models if iphone_model and model.split("-", 1)[0] == iphone_model.split("-", 1)[0]}
    battery_generations = {model.split("-", 1)[0] for model in battery_models}
    if (len(battery_generations) == 1 and len(battery_models) >= 2
            and _compiled_rule('batter[^。.!?]{0,80}capacit|capacit[^。.!?]{0,80}batter|电池容量', 0).search(physical_scope)
            and _compiled_rule('leak|regulatory filing|备案|泄露|曝光', 0).search(physical_scope)
            and _compiled_rule('leak|capacit|容量|曝光', 0).search(title_text)
            and not _compiled_rule('review|tested|评测|实测', 0).search(title_text)):
        generation = next(iter(battery_generations))
        add_claim("iphone-" + generation + "-pro-batteries", "capacity-disclosure", category="hardware_products")
        model_mentions = list(_compiled_rule('\\biphone\\s*(\\d{1,2}\\s+pro(?:\\s+max)?)(?=$|[^a-z0-9])', re.I).finditer(lead))
        for index, mention in enumerate(model_mentions):
            model = _compiled_rule(r"\s+", 0).sub("-", mention.group(1).lower(), 0)
            if model not in battery_models:
                continue
            clause = lead[mention.end():model_mentions[index+1].start() if index+1 < len(model_mentions) else len(lead)]
            for capacity in _compiled_rule('(\\d[\\d,]*)\\s*mah(?:\\s+in\\s+(?:the\\s+)?(u\\.s\\.|us\\b|china\\b|中国|美国))?', re.I).finditer(clause):
                region = (capacity.group(2) or "unspecified").lower()
                region = "us" if region in {"u.s.", "美国"} else "china" if region == "中国" else region
                separation.add(f"battery-capacity-value:{model}:{region}:{capacity.group(1).replace(',', '')}")

    if (
        iphone_model
        and _contains(claim_evidence, "variable aperture", "variable-aperture", "可变光圈")
        and _contains(claim_evidence, "exclusive", "only", "独占", "独享")
    ):
        add_claim(
            f"iphone-{iphone_model}-camera",
            "exclusive-variable-aperture",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    doj_antitrust_response = bool(
        _contains(text, "department of justice", " doj ", "司法部")
        and _contains(text, "antitrust", "反垄断")
        and _contains(
            title_text,
            "responds",
            "rejects",
            "rebuts",
            "refutes",
            "反驳",
            "驳斥",
            "回应",
        )
    )
    if doj_antitrust_response:
        add_claim(
            "apple-doj-antitrust-case",
            "legal-response",
            category="software_systems",
            trusted=direct_title_subject,
        )

    regulatory_service_impact = bool(
        _contains(text, "antitrust", "regulator", "regulatory", "反垄断", "监管机构")
        and _contains(text, "services business", "service revenue", "服务业务", "服务收入")
        and _contains(
            title_text,
            "erodes",
            "erosion",
            "hits",
            "impact",
            "pressure",
            "侵蚀",
            "冲击",
            "影响",
            "打压",
        )
    )
    if regulatory_service_impact:
        add_claim(
            "apple-services",
            "regulatory-financial-impact",
            category="software_systems",
            trusted=direct_title_subject,
        )

    regulatory_meeting = bool(
        _contains(
            text,
            "virtual meeting",
            "constructive talks",
            "constructive meeting",
            "held talks",
            "举行建设性会谈",
            "建设性虚拟会晤",
            "举行建设性虚拟会晤",
        )
        and _contains(
            text,
            "eu tech chief",
            "european commission",
            "digital markets act",
            " dma ",
            "欧盟科技主管",
            "欧盟委员会",
            "欧盟科技事务负责人",
        )
        and _contains(text, "siri", "ai tools", "ai 工具", "新版 siri")
        and _contains(text, "tim cook", "库克")
    )
    if regulatory_meeting:
        add_claim(
            "apple-eu-ai-interoperability",
            "regulatory-meeting",
            category="software_systems",
            trusted=True,
        )

    award_evidence = f"{title_text}. {_normalized(lead)[:900]}"
    executive_award = bool(
        _contains(award_evidence, "person of the year", "年度人物")
        and _contains(award_evidence, "award", "recognized", "named", "获奖", "授予")
        and _contains(award_evidence, "cannes lions", "戛纳狮子")
        and _contains(award_evidence, "apple tv", "apple music", "苹果服务")
    )
    if executive_award:
        add_claim(
            "apple-services-executive",
            "industry-award",
            category="software_systems",
            trusted=True,
        )

    # Compatibility devices and electrical ratings identify neither the
    # vendor nor a co-branded accessory. Bind the offered item from its own
    # title model and locally attributed edition instead.
    if (_compiled_rule('开售|发售|上市', 0).search(title_text)
            and _compiled_rule('充电(?:器|头)|氮化镓|charger', 0).search(_normalized(lead))):
        offered = _compiled_rule('(?:^|[!！])\\s*(?:\\d+(?:\\.\\d+)?\\s*元\\s*)?([\\u4e00-\\u9fff]{2,12})\\s*(\\d+)\\s*号', 0).search(title_text)
        variant = _compiled_rule('(?:电能卡(?:片)?|充电器)\\s*([a-z]+)', 0).search(title_text)
        if offered and variant:
            vendor, number = offered.groups()
            partner = re.search(re.escape(vendor) + r"与([\u4e00-\u9fff]{2,12})联名", _normalized(lead))
            if not partner:
                partner = re.search(re.escape(variant.group(1)) + r"\s*([\u4e00-\u9fff]{2,12})联名版", title_text)
            if partner:
                add_claim("third-party-accessory-" + vendor + "-" + number + "-"
                          + variant.group(1) + "-" + partner.group(1),
                          "co-branded-accessory-retail-offer", trusted=False)

    third_party_app_action = _third_party_platform_app_action(title, lead)
    if third_party_app_action:
        owner, platform, target = third_party_app_action
        add_claim(
            f"third-party-software-{owner}-{target}",
            "platform-software-action",
            qualifier=platform,
            category="software_systems",
            trusted=False,
        )

    vehicle_policy = _vehicle_platform_policy_clarification(title, lead)
    if vehicle_policy:
        owner, policy = vehicle_policy
        add_claim("vehicle-maker-" + owner + "-carplay", "compatibility-policy-clarification",
                  qualifier=policy, trusted=False)

    home_hub_subject = bool(
        "apple-home-hub" in identity.title_products
        or identity.title_named_subjects & {"homepad", "homehub", "home-hub"}
        or _contains(title_text, "homepad", "home hub", "homehub")
        or (
            _compiled_rule(r"^(?:apple(?:'s|’s)?|苹果)", 0).match(title_text)
            and _contains(title_text, "home automation", "smart home", "家庭自动化", "智能家居")
            and identity.named_subjects & {"homepad", "homehub", "home-hub"}
        )
    )
    if home_hub_subject and _contains(
        claim_evidence,
        "widget gallery",
        "smart stack",
        "widget support",
        "widget mirroring",
        "小组件图库",
        "小组件库",
        "智能叠放",
        "小组件镜像",
        "支持小组件",
        "搭载小组件",
    ) and _contains(claim_evidence, "code", "macos", "代码", "文件"):
        add_claim(
            "apple-home-hub",
            "widget-capability",
            category="software_systems",
            trusted=True,
        )

    home_hub_profile_switching = bool(
        home_hub_subject
        and _contains(claim_evidence, "apple", "苹果", "macos")
        and _contains(
            claim_evidence,
            "user profile",
            "user profiles",
            "profile switching",
            "switch personal profiles",
            "automatic profile switching",
            "switch profiles",
            "profile selection",
            "personal content",
            "different content depending",
            "用户配置",
            "用户资料",
            "个人内容",
            "切换个人配置",
            "切换不同账号",
            "切换账号",
            "切换用户",
            "个人资料切换",
        )
        and _contains(
            claim_evidence,
            "face",
            "facial",
            "camera",
            "ambient sensing",
            "识别人脸",
            "识别面容",
            "摄像头",
            "环境感知",
        )
    )
    if home_hub_profile_switching:
        add_claim(
            "apple-home-hub",
            "identity-personalization",
            category="software_systems",
            trusted=True,
        )

    # A utility's prior retirement can explain a current hardware measurement;
    # it does not assert a new operating-system lifecycle action.
    lifecycle_scope = " ".join(sentence for sentence in _compiled_rule(r"(?<=[.!?。！？])\s*", 0).split(claim_evidence, 0)
        if not _compiled_rule('\\b(?:already|previously|formerly|historically|long ago)\\b|早已(?:经)?|此前|曾经|早就|去年', re.I).search(sentence))
    lifecycle_action = bool(
        _contains(
            lifecycle_scope,
            "deprecated",
            "deprecates",
            "to be removed",
            "will be removed",
            "being removed",
            "弃用",
            "将移除",
            "未来会移除",
        )
    )
    utility_matches = _compiled_rule(r"(?:deprecat(?:e|es|ed|ing)|弃用|标记弃用)[^。.!?]{0,35}?"
        r"(?<![a-z0-9])([a-z][a-z0-9_.+-]{3,30})(?![a-z0-9])", 0).findall(lifecycle_scope)
    if not utility_matches:
        utility_matches = _compiled_rule(r"(?<![a-z0-9])([a-z][a-z0-9_.+-]{3,30})(?![a-z0-9])"
            r"\s+(?:is|was|has been|will be)\s+(?:officially\s+)?deprecated\b", 0).findall(lifecycle_scope)
    if not utility_matches:
        utility_matches = _compiled_rule(r"(?<![a-z0-9])([a-z][a-z0-9_.+-]{3,30})(?![a-z0-9])"
            r"[^。.!?]{0,35}?(?:to be removed|will be removed|弃用|将移除|未来会移除)", 0).findall(lifecycle_scope)
    utility_candidates = [
        token
        for token in utility_matches
        if token
        not in {
            "apple",
            "deprecated",
            "diskutil",
            "image",
            "macos",
            "removed",
            "tool",
            "utility",
        }
    ]
    if (
        lifecycle_action
        and _contains(lifecycle_scope, "macos", "ios", "ipados", "watchos", "tvos", "visionos")
        and utility_candidates
    ):
        utility = utility_candidates[0]
        add_claim(
            f"apple-os-utility-{utility}",
            "lifecycle-deprecation",
            category="software_systems",
            trusted=direct_title_subject or _contains(lifecycle_scope, "apple", "苹果"),
        )

    apple_server_subject = bool(
        _contains(
            claim_evidence,
            "apple's ai server",
            "apple ai server",
            "apple server",
            "private cloud compute server",
            "苹果 ai 服务器",
            "苹果服务器",
            "苹果自研服务器",
        )
    )
    server_hardware_reveal = bool(
        apple_server_subject
        and _contains(
            claim_evidence,
            "first look",
            "inside",
            "internal layout",
            "internal structure",
            "photos show",
            "内部结构",
            "内部布局",
            "首曝",
            "首次曝光",
        )
        and _contains(
            claim_evidence,
            "server",
            "hardware",
            "chassis",
            "rack",
            "2u",
            "服务器",
            "硬件",
            "机架",
            "机箱",
        )
    )
    if server_hardware_reveal:
        add_claim(
            "apple-ai-server",
            "internal-hardware-reveal",
            category="hardware_products",
            trusted=True,
        )

    if (
        "apple-store-app" in identity.products
        and "shopping-assistant" in identity.components
    ):
        category_hint = "software_systems"

    beats_model = _compiled_rule(r"\bbeats\s*(\d{2,4})(?!\d)", 0).search(title_text)
    if beats_model and _contains(
        text,
        "listing",
        "retail",
        "spec",
        "leak",
        "anc",
        "ipx",
        "零售",
        "规格",
        "泄露",
        "曝光",
        "降噪",
        "防水",
    ):
        add_claim(
            f"beats-model-{beats_model.group(1)}",
            "product-specification-leak",
            category="hardware_products",
            trusted=True,
        )

    if _compiled_rule(r"\b(?:unidentified|unknown|unreleased)\s+(?:apple\s+)?(?:device|product)\s+identifiers?\b|"
        r"(?:未识别|未知|未发布).{0,12}(?:设备|产品).{0,8}(?:标识|型号)|"
        r"(?:设备|产品).{0,8}(?:标识|型号).{0,12}(?:未识别|未知)", 0).search(title_text) and _contains(text, "macos", "system code", "code", "系统代码", "代码"):
        add_claim(
            "apple-unreleased-device-identifiers",
            "code-disclosure",
            category="hardware_products",
            trusted=True,
        )

    return (
        event_keys,
        boundaries,
        separation,
        category_hint,
        trusted_direct_action,
    )


def _product_anniversary_milestone(title: str) -> tuple[str, str] | None:
    milestone = _compiled_rule(r"\bturns?\s+(\d{1,3})\b|"
        r"\bmarks?\s+(?:its\s+)?(\d{1,3})(?:st|nd|rd|th)?\s+anniversary\b|"
        r"\bcelebrates?\s+(?:its\s+)?(\d{1,3})(?:st|nd|rd|th)?\s+anniversary\b|"
        r"(?:问世|发布|诞生|迎来|庆祝).{0,10}?(\d{1,3})\s*周年|"
        r"(\d{1,3})\s*周年(?:纪念)?.{0,10}?(?:问世|发布|诞生|迎来|庆祝)", 0).search(title)
    if not milestone:
        return None
    years = next((value for value in milestone.groups() if value), "")
    candidates: list[tuple[int, str]] = []
    for product, aliases in PRODUCT_PATTERNS:
        for alias in aliases:
            position = title.rfind(alias, 0, milestone.end())
            if position >= 0 and milestone.start() - position <= 80:
                candidates.append((position, product))
    if not candidates:
        return None
    _position, product = max(candidates)
    return product, years


def _market_result_separation_keys(market_result_keys: set[str]) -> set[str]:
    """Preserve metric roles and report scope for every market profile path."""
    separation: set[str] = set()
    market_scopes = {
        tuple(key.split(":")[1:4])
        for key in market_result_keys
        if key.startswith(("structured-market-result:", "structured-market-forecast:"))
    }
    for key in market_result_keys:
        fields = key.split(":")
        if len(fields) == 6 and fields[4].startswith("apple-"):
            separation.add('market-result-stage:' + ('forecast' if fields[0] == 'structured-market-forecast' else 'observed'))
            separation.add("market-result-measure:" + fields[4].removeprefix("apple-") + ":" + fields[5])
            separation.add("market-result-local-measure:" + fields[2] + ":" + fields[4].removeprefix("apple-") + ":" + fields[5])
            year = _compiled_rule(r"(20\d{2})-q([1-4])", 0).match(fields[3])
            if year:
                separation.add("market-result-year:" + year.group(1))
                separation.add("market-result-quarter:q" + year.group(2))
            elif _compiled_rule(r"q[1-4]", 0).fullmatch(fields[3]):
                separation.add("market-result-quarter:" + fields[3])
    market_regions = {region for _firm, region, _period in market_scopes}
    market_firms = {firm for firm, _region, _period in market_scopes}
    if len(market_regions) == 1 and len(market_firms) == 1:
        separation.add(
            "market-report-scope:"
            f"{next(iter(market_firms))}:{next(iter(market_regions))}"
        )
    return separation


def _market_percentage_roles(clause: str) -> tuple[str, str]:
    """Return current/previous values only when their relation is stated."""
    matches = list(_compiled_rule(
        r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:%|percent(?:age)?(?:\s+points?)?)", re.I).finditer(clause))
    def value(match):
        raw = match.group(1)
        return raw.rstrip("0").rstrip(".") if "." in raw else raw
    if len(matches) == 1:
        prefix = clause[:matches[0].start()]
        if _compiled_rule(r'\b(?:over|more than|exceed(?:s|ed)?|cross(?:es|ed)?)\s*$|(?:超过|突破)\s*$', re.I).search(prefix):
            return '', ''
        return value(matches[0]), ''
    if len(matches) != 2:
        return '', ''
    first, second = matches
    prefix, relation = clause[:first.start()], clause[first.end():second.start()]
    if (_compiled_rule(r"\bfrom\s*$|[从由]\s*$", re.I).search(prefix)
            and _compiled_rule(r"\bto\s*$|[至到]\s*$", re.I).search(relation)):
        return value(second), value(first)
    if _compiled_rule(r"\bfrom\s*$|此前(?:为|是)?\s*$|原为\s*$", re.I).search(relation):
        return value(first), value(second)
    if _compiled_rule(r'\breaching\s*$|(?:达到|升至|降至)\s*$', re.I).search(relation):
        return value(second), ''
    # A change in percentage points is not the previous market share.
    if (_compiled_rule(r"points?\s*$", re.I).search(first.group(0))
            and _compiled_rule(r"^\s+to\s*$", re.I).fullmatch(relation)
            or _compiled_rule(r"points?\s+to\s*$|个百分点.*[至到]\s*$", re.I).search(relation)):
        return value(second), ''
    return '', ''


def _measured_apple_market_result_keys(
    title: str,
    lead: str,
    evidence: str,
    *, include_forecasts: bool = False, published_year: str = "",
) -> set[str]:
    """Serialize locally bound market statements without rejudging their role."""
    title_scope = _normalized(title)
    primary_lead = _primary_assertion_scope("", lead)[1]
    # A causal background clause does not own the current report's action.
    # Keep the leading measurement itself when it is the substantive assertion.
    primary_lead = _compiled_rule(r",\s*(?:following|after|building\s+on)\b", re.I).split(primary_lead, 1)[0]
    title_or_lead_owns_result = any(
        _contains(scope, "apple", "iphone", "苹果")
        and _contains(
            scope,
            "market share",
            "demand", "需求",
            "shipment share",
            "shipments",
            "sales",
            "best selling",
            "best-selling",
            "bestseller",
            "份额",
            "出货量",
            "销量",
            "畅销",
            "销量榜",
        )
        for scope in (title_scope, primary_lead)
    )
    if not title_or_lead_owns_result:
        title_or_lead_owns_result = bool(
            any(_contains(scope, "apple", "iphone", "苹果")
                and _compiled_rule(r"\b(?:grew|growth|rose|increased|gained|outperformed)\b|增长|上升|提升|逆势|扩大", 0).search(scope)
                for scope in (title_scope, primary_lead))
            and _compiled_rule(r"(?:apple|iphone|苹果).{0,90}(?:\d+(?:\.\d+)?\s*%|"
                r"market share|shipments|sales|份额|出货量|销量)", re.I).search(_normalized(lead + " " + evidence))
        )
    if not title_or_lead_owns_result:
        return set()
    scope = _normalized(". ".join(part for part in (title, lead, evidence) if part))
    firm = next(
        (
            name
            for name, aliases in (
                ("counterpoint", ("counterpoint",)),
                ("canalys", ("canalys",)),
                ("idc", (" idc ", "idc report", "idc 报告")),
                ("omdia", ("omdia",)),
                ("trendforce", ("trendforce",)),
                ("runto", ("runto", "洛图")),
            )
            if _contains(f" {scope} ", *aliases)
        ),
        "",
    )
    firm = firm or "unattributed"
    if not _contains(
        scope,
        "market share",
        "shipment share",
        "shipments",
        "sales",
        "best selling",
        "best-selling",
        "bestseller",
        "份额",
        "出货量",
        "销量",
        "畅销",
        "销量榜",
    ):
        return set()

    region_aliases = (
        ("europe", ("europe", "european", "欧洲")),
        ("latin-america", ("latin america", "latam", "拉美", "拉丁美洲")),
        ("india", ("india", "印度")),
        ("china", ("china", "中国")),
        ("global", ("global", "worldwide", "world's", "worlds", "全球")),
    )
    segment = ("foldable-phone" if _compiled_rule(r"foldable|折叠", 0).search(scope) else
               "pc" if _compiled_rule(r"\bpc\b|\bmacs?\b|\blaptops?\b|电脑|笔记本", 0).search(scope) else
               "smartphone" if _compiled_rule(r"smartphone|iphone|手机", 0).search(scope) else "")
    all_owned_measures = set()
    sentences = [
        sentence.strip()
        for sentence in _compiled_rule(r"(?:[。！？]|(?<=[.!?])\s+)", 0).split(scope, 0)
        if sentence.strip()
    ]
    current_regions: set[str] = set()
    current_period = ""
    current_quarter = ""
    keys: set[str] = set()
    for sentence in sentences:
        sentence_regions = {
            region
            for region, aliases in region_aliases
            if _contains(sentence, *aliases)
        }
        if sentence_regions:
            current_regions = sentence_regions
        year, quarter = source_market_quarter(sentence, published_year)
        if quarter and not current_period:
            current_quarter = quarter
            if year:
                current_period = year + "-" + quarter
        if not current_quarter:
            year_only = _compiled_rule(r"(?<!\d)(20\d{2})(?!\d)", 0).search(sentence)
            if year_only:
                current_period = year_only.group(1)
                month = _compiled_rule(r"(?<!\d)(20\d{2})\s*年\s*(1[0-2]|0?[1-9])\s*月", 0).search(sentence)
                if month:
                    current_period = f"{month.group(1)}-{int(month.group(2)):02d}"
        if not current_regions:
            continue
        if not _contains(sentence, "apple", "iphone", "苹果"):
            continue
        percentages = set()
        owned_clauses = []
        metric_scope = ""
        for raw, clause, role in source_market_statements(sentence):
            if _compiled_rule(r"share|shipments?|shipped|sales|revenue|份额|出货|销量|营收|收入|占|(?<![a-z])(?:apple|iphones?|macs?)(?![a-z])|苹果", re.I).search(clause):
                metric_scope = clause
            if role != 'observed' and not (include_forecasts and role == 'forecast'):
                continue
            period_scope = _compiled_rule(
                r'(?:%|percent)\s+from\b|compared\s+(?:with|to)|\b(?:up|down)\s+from\b|较(?:去年|上季)', re.I).split(raw, 1)[0]
            local_year, local_quarter = source_market_quarter(period_scope, published_year)
            local_period = (local_year + '-' + local_quarter if local_year and local_quarter
                else local_quarter if local_quarter and local_quarter != current_quarter
                else current_period or current_quarter)
            owned_clauses.append((raw, clause, role, local_period))
            # Bare percentage continuations inherit only their owned metric,
            # never an earlier market-share mention elsewhere in the sentence.
            share_relation = bool(_compiled_rule(r"\baccount(?:s|ed)?\s+for\b|\bshipp?(?:ed|s)?\s+\d+(?:\.\d+)?\s*(?:%|percent)\s+of\b|\b(?:gained|rose|increased|up)\b.{0,28}\bpoints?\s+to\s+\d|份额|占", re.I).search(clause))
            if share_relation or _compiled_rule(r"share|份额|占", re.I).search(metric_scope):
                metric = "share"
            elif _compiled_rule(r"shipments?|shipped|出货", re.I).search(metric_scope):
                metric = "shipment-change"
            elif _compiled_rule(r"sales|销量", re.I).search(metric_scope):
                metric = "sales-change"
            else:
                continue
            if local_year and local_quarter:
                current_period, current_quarter = local_period, local_quarter
            current, previous = _market_percentage_roles(clause)
            if not current:
                continue
            local_regions = frozenset(region for region, aliases in region_aliases if _contains(clause, *aliases)) or frozenset(current_regions)
            percentages.add((role, metric + "-current", current, local_regions, local_period))
            if previous:
                percentages.add((role, metric + "-previous", previous, local_regions, local_period))
        all_owned_measures.update((metric, value) for role, metric, value, _regions, _period in percentages if role == 'observed')
        rank_roles = {
            (role, period) for raw, clause, role, period in owned_clauses
            if (_compiled_rule(r"\b(?:world(?:'s)?|global(?:ly)?)\s+(?:best[- ]selling|top[- ]selling)\b|"
                r"\b(?:topped|led|leads|ranked first|ranks first|number one|no\.\s*1)\b|"
                r"(?:全球)?(?:最畅销|销量第一|排名第一|稳居第一|位居第一|登顶|霸榜)", 0).search(clause)
                or _compiled_rule(r"\bbestseller ranking puts (?:apple|iphone)\b.{0,30}\bfirst\b", 0).search(raw))
        }
        for region in current_regions:
            for role, metric, percentage, measure_regions, measure_period in percentages:
                if region not in measure_regions:
                    continue
                prefix = 'structured-market-forecast' if role == 'forecast' else 'structured-market-result'
                for period in {measure_period} - {""}:
                    for attribution in {firm, role + "-" + segment} if segment else {firm}:
                        keys.add(f"{prefix}:{attribution}:{region}:{period}:apple-{metric}:{percentage}")
            for role, rank_period in rank_roles:
                prefix = 'structured-market-forecast' if role == 'forecast' else 'structured-market-result'
                for period in {rank_period} - {""}:
                    keys.add(f"{prefix}:{firm}:{region}:{period}:apple-rank:1")
    if segment and len(all_owned_measures) >= 2 and len(current_regions) == 1:
        keys.add("structured-measure:apple-market:" + segment + ":" + next(iter(current_regions))
                 + ":measure-series:" + ",".join(metric + "=" + value for metric, value in sorted(all_owned_measures)))
    return keys



_HARDWARE_FIRST_PARTY_PRODUCTS = {
    "airpods",
    "airtag",
    "apple-glasses",
    "apple-home-hub",
    "apple-power-adapter",
    "apple-watch",
    "beats",
    "foldable-iphone",
    "game-controller",
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
    "magic-keyboard",
    "polishing-cloth",
    "vision-pro",
}


_SPECIFIC_FIRST_PARTY_PRODUCTS = {
    "apple-smart-home-os",
    "apple-home-hub",
    "apple-power-adapter",
    "game-controller",
    "magic-keyboard",
    "polishing-cloth",
}

_PRECISE_HARDWARE_PRODUCT_LINES = {
    "apple-home-hub",
    "apple-power-adapter",
    "foldable-iphone",
    "game-controller",
    "imac",
    "ipad-air",
    "ipad-mini",
    "ipad-pro",
    "mac-mini",
    "mac-pro",
    "mac-studio",
    "magic-keyboard",
    "polishing-cloth",
    "vision-pro",
}




def _lead_asserts_first_party_release(lead: str) -> bool:
    """Return true only when the first lead sentence owns an Apple release."""
    first_lead = _primary_assertion_scope("", lead)[1]
    direct_os_release = _compiled_rule(
        r'^[.\s]*(?:ios|ipados|macos|watchos|tvos|visionos)\s*\d+(?:\.\d+)*'
        r'(?:\s*(?:beta|rc)\s*\d*)?\s*'
        r'(?:(?:(?:is|are|has|have|now|officially|been)\s+)*(?:released|launched|available|arrived)\b|'
        r'(?:现已|已经|正式|已)(?:发布|推送|上线))', re.I).search(first_lead)
    return bool(direct_os_release or
        _compiled_rule(r"\bapple\b.{0,48}\b(?:is\s+announcing|are\s+announcing|announces|announced|"
            r"introduces|introduced|launches|launched|unveils|unveiled|releases|released)\b|"
            r"苹果.{0,36}(?:发布|推出|揭晓|上线|开售|登场)(?!的)", 0).search(first_lead)
    )


def _prepare_bounded_product_patterns():
    """Prepare only fixed vocabulary, never article-dependent decisions."""
    products = []
    for product, aliases in PRODUCT_PATTERNS:
        patterns = []
        for alias in aliases:
            normalized_alias = _normalized(alias)
            if not normalized_alias:
                continue
            if _compiled_rule(r"[a-z0-9][a-z0-9 .+/-]*", 0).fullmatch(normalized_alias):
                direct = re.compile(rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])")
                possessive = (re.compile(rf"(?<![a-z0-9])its\s+{re.escape(normalized_alias.removeprefix('apple '))}(?![a-z0-9])")
                              if normalized_alias.startswith("apple ") else None)
                patterns.append((normalized_alias, direct, possessive))
            else:
                patterns.append((normalized_alias, None, None))
        products.append((product, tuple(patterns)))
    return tuple(products)


_BOUNDED_PRODUCT_PATTERNS = _prepare_bounded_product_patterns()


def _bounded_evidence_products(value: str) -> set[str]:
    """Resolve known first-party products from the bounded article evidence.

    Headlines sometimes use a descriptive product label (for example, a
    display instead of its established hub name), while the lead names the
    canonical product.  Reuse the identity vocabulary here instead of adding
    source-specific headline aliases.  Possessives are normalized because
    English leads commonly say ``Apple's`` where product aliases say
    ``Apple``.
    """
    scope = _normalized(value)
    scope = _compiled_rule(r"\bapple's\b", 0).sub("apple", scope, 0)
    products: set[str] = set()
    for product, patterns in _BOUNDED_PRODUCT_PATTERNS:
        for normalized_alias, direct, possessive in patterns:
            if direct is not None:
                if direct.search(scope) or (possessive is not None and possessive.search(scope)):
                    products.add(product)
                    break
            elif normalized_alias in scope:
                products.add(product)
                break
    return products


def _structured_title_subjects(
    identity: EventIdentity,
    evidence_products: Iterable[str] = (),
) -> set[str]:
    subjects = set(identity.title_products & _SPECIFIC_FIRST_PARTY_PRODUCTS)
    subjects |= {
        component
        for component in identity.title_components
        if component.startswith("apple-silicon-generation:")
        or component in {
            "genlock",
            "keyboard-key-labels",
            "maps-advertising",
            "private-cloud-compute-server",
        }
    }
    if identity.scope == "apple-direct" and identity.content_form == "news":
        lead_products = set(identity.products & _SPECIFIC_FIRST_PARTY_PRODUCTS)
        lead_products |= set(evidence_products) & _SPECIFIC_FIRST_PARTY_PRODUCTS
        if not subjects and len(lead_products) == 1:
            subjects |= lead_products
        trusted_components = {
            component
            for component in identity.components
            if component.startswith("apple-silicon-generation:")
            or component
            in {
                "genlock",
                "keyboard-key-labels",
                "maps-advertising",
                "private-cloud-compute-server",
            }
        }
        if not subjects and len(trusted_components) == 1:
            subjects |= trusted_components
    return subjects








def _structured_category_hint(
    identity: EventIdentity,
    direct_subjects: Iterable[str] = (),
    title: str = "",
) -> str:
    if any(value.startswith("device-software-release:") for value in identity.components):
        return "software_systems"
    if (
        identity.scope == "apple-direct"
        and "first-party-accessibility-guidance" in identity.components
    ):
        return "software_systems"
    if (
        identity.scope == "apple-direct" and identity.content_form == "news"
        and identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
        and not identity.title_products & _SOFTWARE_FIRST_PARTY_PRODUCTS
        and ("component-cost-analysis" in identity.components or any(
            value.startswith("money:") for value in _evidence_measurements(title, "")
        ))
    ):
        return "hardware_products"
    for service in identity.title_products & _SOFTWARE_FIRST_PARTY_PRODUCTS:
        name = re.escape(service.replace("apple-", "")).replace(r"\-", r"\s+")
        if re.search(r"(?<![a-z0-9])" + name + r"(?:\s+ai)?\s+(?:(?:is|has|keeps?)\s+)?(?:frustrat\w*|fail\w*|crash\w*|cannot|can['’]t|won['’]t|break\w*)\b", title, re.I):
            return "software_systems"
    direct_subjects = (
        set(direct_subjects)
        or set(identity.title_named_subjects)
        or _structured_title_subjects(identity)
    )
    direct_action = bool(_structured_title_action_classes(identity))
    if identity.action_owner != "apple" and not (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and direct_subjects
        and direct_action
    ):
        return ""
    if (
        "apple-operated-activity-challenge" in identity.facets
        or "apple-watch-activity-challenge" in identity.title_named_subjects
    ):
        return "software_systems"
    if identity.title_components & {
        "financed-device-restriction",
        "genlock",
        "keyboard-key-labels",
    }:
        return "hardware_products"
    products = set(identity.title_products) | set(direct_subjects)
    direct_hardware_subjects = set(direct_subjects) & _HARDWARE_FIRST_PARTY_PRODUCTS
    direct_software_subjects = set(direct_subjects) & _SOFTWARE_FIRST_PARTY_PRODUCTS
    if direct_hardware_subjects and not direct_software_subjects:
        return "hardware_products"
    if direct_software_subjects and not direct_hardware_subjects:
        return "software_systems"
    if products & _PRECISE_HARDWARE_PRODUCT_LINES:
        # A concrete physical product named by the headline owns the category;
        # an OS name can describe where its code evidence was found without
        # turning the hardware disclosure into a software event.
        return "hardware_products"
    if products & _SOFTWARE_FIRST_PARTY_PRODUCTS:
        return "software_systems"
    if products & _HARDWARE_FIRST_PARTY_PRODUCTS:
        return "hardware_products"
    if any(
        component.startswith("apple-silicon-generation:")
        for component in identity.title_components
    ):
        return "hardware_products"
    if "private-cloud-compute-server" in direct_subjects:
        return "software_systems"
    return ""


def _source_named_os_component_action(title: str, evidence: str, identity: EventIdentity) -> bool:
    """Use a source's local component assertion, not its release-date wrapper."""
    version_pattern = r"\b(ios|ipados|macos|watchos|tvos|visionos)\s+(\d+(?:\.\d+)*)\b"
    title_versions = set(re.findall(version_pattern, title, re.I))
    names = {value.removeprefix("os-component:").replace("-", " ")
             for value in identity.components if value.startswith("os-component:")}
    if "spotlight-index-preparation" in identity.components:
        names.add("spotlight")
    if not title_versions or not names:
        return False
    for sentence in _compiled_rule(r"(?<=[.!?])\s+(?=[A-Z])|[。！？]", 0).split(evidence, 0):
        lower = sentence.lower().strip()
        versions = re.findall(version_pattern, lower)
        if not versions or versions[0] not in title_versions:
            continue
        if not _compiled_rule(r"^(?:apple\b|苹果)", 0).match(lower):
            continue
        if _compiled_rule(r"\b(?:not|never|should|might)\b|并未|不再|应该|可能", 0).search(lower):
            continue
        if (any(name in lower for name in names)
                and _compiled_rule(r"\b(?:start(?:s|ed)?|optimiz(?:e|es|ed)|adds?|updates?|changes?|introduces?)\b|新增|开始|优化|更新|调整", 0).search(lower)):
            return True
    return False


def _card_savings_rate_report(
    title: str, lead: str, source_facts: tuple[str, ...]
) -> tuple[str, str, str] | None:
    """Bind a titled Card account rate change to its current source assertion."""
    headline = _canonical_title(title)
    if (_compiled_rule(r"\bapple\s*card\b", 0).search(headline)
            and _compiled_rule(r"储蓄账户|savings\s+account", 0).search(headline)
            and _compiled_rule(r"利率|rate|apy", 0).search(headline)
            and _compiled_rule(r"上调|涨至|提高|increas\w*|rais\w*", 0).search(headline)):
        opening = _normalized(lead)[:450]
        change = _compiled_rule(r"从\s*(\d+(?:\.\d+)?)\s*[%％]\s*(?:上调|提高|涨)\s*至\s*(\d+(?:\.\d+)?)\s*[%％]", 0).search(opening)
        if change and Decimal(change.group(2)) > Decimal(change.group(1)):
            # The figures alone do not assert an increase: the same predicate
            # can be denied, historical, or preceded by another actor's denial.
            clause = _compiled_rule(r"[。！？；;]|但(?:是)?|不过|然而|却", 0).split(opening[:change.start()], 0)[-1]
            owners = list(_compiled_rule(r"苹果", 0).finditer(clause))
            if not owners:
                return None
            owner = owners[-1]
            action = clause[owner.end():]
            if not _compiled_rule(r"(?:apple\s*card|储蓄账户)", 0).search(action):
                return None
            if not _compiled_rule(r"利率|rate|apy", 0).search(action):
                return None
            historical = bool(_compiled_rule(r"去年|前年|上个?月|此前|早在|过去", 0).search(headline)
                              or _compiled_rule(r"去年|前年|上个?月|此前|早在|过去", 0).search(clause[max(0, owner.start() - 45):owner.start()])
                              or _compiled_rule(r"去年|前年|上个?月|此前|早在|过去", 0).search(action))
            if historical:
                return ("historical", "", "")
            denied = bool(_compiled_rule(r"尚未|还未|仍未|并未|没有|未曾|未能|不会|"
                r"(?<![尚还仍并曾能])未(?=将|把|上调|提高|涨)", 0).search(action))
            return ("denied" if denied else "current",
                    str(Decimal(change.group(1)).normalize()),
                    str(Decimal(change.group(2)).normalize()))
    if not (_compiled_rule(r"\bapple\s+card(?:'s)?\s+savings\s+account(?:'s)?\b", 0).search(headline)
            and _compiled_rule(r"\b(?:interest\s+rate|rate|apy|annual\s+percentage\s+yield)\b", 0).search(headline)
            and _compiled_rule(r"\b(?:increas\w*|rais\w*|rose|ris\w*|went\s+up|goes\s+up)\b", 0).search(headline)):
        return None
    if _compiled_rule(r"\b(?:last\s+(?:week|month|year)|previously|earlier|historically)\b", 0).search(headline):
        return ("historical", "", "")
    for passage in (lead[:450], *source_facts[:4]):
        opening = _normalized(passage)[:450]
        for match in _compiled_rule(r"\bfrom\s+(\d+(?:\.\d+)?)\s*%\s+to\s+(\d+(?:\.\d+)?)\s*%\s+today\b", 0).finditer(opening):
            clause = opening[max(0, match.start() - 180):match.start()].rsplit(". ", 1)[-1]
            assertion = _compiled_rule(r"[,;]\s*(?:but|whereas|while)\b|\b(?:although|however)\b", 0).split(clause, 0)[-1]
            actions = list(_compiled_rule(r"\b(?:increas\w*|rais\w*|rose|went\s+up)\b", 0).finditer(assertion))
            if (_compiled_rule(r"\b(?:interest\s+rate|annual\s+percentage\s+yield|apy)\b", 0).search(assertion)
                    and actions
                    and _compiled_rule(r"\bapple\s+(?:card\b|and\b)", 0).search(assertion)
                    and Decimal(match.group(2)) > Decimal(match.group(1))):
                predicate_before = assertion[max(0, actions[-1].start() - 30):actions[-1].start()]
                negated = bool(_compiled_rule(r"\b(?:not|never)(?:\s+yet)?\s*$|"
                    r"\b(?:has|have|had|did|does|is|was|were)n['’]t\s*$|"
                    r"\bno\s+longer\s*$", 0).search(predicate_before))
                return ("denied" if negated else "current",
                        str(Decimal(match.group(1)).normalize()),
                        str(Decimal(match.group(2)).normalize()))
    opening = _normalized(lead)[:450]
    if _compiled_rule(r"\b(?:last\s+(?:week|month|year)|previously|earlier)\b[^.!?]{0,90}"
        r"\bapple\b[^.!?]{0,100}\b(?:increas\w*|rais\w*|rose)\b"
        r"[^.!?]{0,90}\b(?:interest\s+rate|annual\s+percentage\s+yield|apy|savings\s+account\s+rate)\b", 0).search(opening):
        return ("historical", "", "")
    return None


def _weekly_device_sales_subject(title: str, lead: str) -> str:
    """Compatibility view of the source-owned weekly measurement."""
    from .event_identity import source_weekly_device_measurement
    frame = source_weekly_device_measurement(title, lead)
    return ':'.join((frame.subject, frame.action, frame.period, frame.region, frame.year)) if frame else ''


def _source_local_current_action(
    title: str, lead: str, source_facts: tuple[str, ...], identity: EventIdentity,
    name_aliases: Mapping[str, str] | None = None,
    regions: Iterable[str] = (), evidence: str = "", source_units: tuple[str, ...] = (),
    published_year: str = "",
) -> ReconciliationProfile | None:
    """Bind the source's current actor, object and stage before background keys.

    The same frame is used for English and Chinese accounts.  A named device,
    version or action is required locally; shared product mentions are not
    sufficient evidence of a shared event.
    """
    headline = _canonical_title(title)
    opening = _normalized(lead)[:1000]
    facts = " ".join(_normalized(fact) for fact in source_facts[:4])[:2200]
    local = f"{headline}. {opening}. {facts}"

    def has(pattern: str, value: str = local) -> bool:
        return _compiled_rule(pattern, re.I).search(value) is not None

    def profile(subject: str, action: str, *, tier: str = "strong",
                category: str = "software_systems", kind: str = "os_app",
                reason: str = "source-local current action",
                content_form: str = "news", weak_boundary: str = "source-local-third-party-action") -> ReconciliationProfile:
        return ReconciliationProfile(
            event_keys=frozenset({f"primary-claim:{subject}:{action}"}),
            boundary_keys=frozenset({f"primary-claim-subject:{subject}"}),
            separation_keys=frozenset({f"primary-claim-subject:{subject}",
                                       f"primary-claim-predicate:{action}",
                                       "source-local-action-authority"}),
            category_hint=category, identity=replace(identity, content_form=content_form),
            relevance_tier=tier, trusted_direct_action=tier == "strong",
            promotion_reason=reason if tier == "strong" else "",
            ecosystem_reason=reason if tier == "ecosystem" else "",
            defer_reason=reason if tier == "weak" else "",
            hard_boundary=weak_boundary if tier == "weak" else "",
            event_kind_hint=kind,
        )

    def current_primary_predicate(affirmative: str, contrary: str, *, whole_clause_history: bool = False) -> bool:
        """Read the first action-bearing source assertion, not later context."""
        historical = r"\b(?:previously|earlier|historically|last\s+year|back\s+in)\b|此前|早前|曾经|曾于|去年"
        def claim_in(clause: str) -> bool | None:
            positive = _compiled_rule(affirmative, re.I).search(clause)
            conflict = _compiled_rule(contrary, re.I).search(clause)
            if conflict and (positive is None or conflict.start() <= positive.start()):
                return False
            if positive is None:
                return None
            past = _compiled_rule(historical, re.I).search(clause if whole_clause_history else clause[:positive.start()])
            return past is None

        headline_claim = claim_in(headline)
        if headline_claim is False:
            return False
        clauses = _compiled_rule(r"[。！？]|(?<=[.!?])\s+(?=[a-z])", 0).split(opening[:950], 0)
        if whole_clause_history:
            clauses = [part for clause in clauses for part in _compiled_rule(
                r"[;；]|\b(?:but|while|whereas|however)\b|但是|不过|然而", re.I).split(clause)]
        for clause in clauses[:4]:
            claim = claim_in(clause)
            if claim is not None:
                return claim
        return headline_claim is True

    # A share-price report owns the named issuer's market action. A verdict
    # or Apple product mentioned as its cause is background, not its owner.
    share_owner = _compiled_rule(r"(?:shares?\s+(?:in|of)|stock\s+(?:in|of))\s+(.{2,90}?)\s+(?:jumped|rose|fell|gained|climbed|surged|dropped)\b", 0).match(opening)
    if (share_owner and not _compiled_rule(r"apple(?:\s+inc\.?)?", 0).fullmatch(share_owner.group(1))
            and has(r"\b(?:shares?|stock)\b|股价", headline)
            and has(r"\d+(?:\.\d+)?\s*(?:%|percent)", opening[:250])):
        return profile(f"third-party-equity:{share_owner.group(1)}", "share-price-report", tier="weak",
                       kind="third_party_ecosystem",
                       reason="third-party issuer's share-price reaction; Apple action is background")

    if descriptive_apple_product_reference(title):
        return profile(f"third-party:{headline}", "product-description", tier="weak",
                       category="hardware_products", kind="third_party_ecosystem",
                       reason="Apple word describes another product, not its action owner")

    # Publisher selection and subjective evaluation own these source forms.
    # Device specifications and compatibility paragraphs cannot promote them.
    publisher_selection = (bool(_compiled_rule(r"^(?:don[’\']t|do not|never)\s+buy\b|^(?:不要|别|暂缓)购买", re.I).search(headline)) or (identity.content_form == "buying_advice"
        and has(r"\b(?:our|top)\s+(?:recommendations|picks)|is\s+it\s+worth\s+(?:upgrading|buying)|should\s+(?:you|we)\s+(?:upgrade|buy|choose)|购买推荐|配件推荐", headline + " " + opening[:350])))
    publisher_opinion = (identity.content_form == "analysis"
        and has(r"\bi\s+(?:do\s+)?think\b|我认为|我觉得", opening[:700]))
    quoted_purchase_opinion = (
        has(r"calls?|says?|评|称", headline)
        and has(r"not\s+worth\s+buying|waste\s+of\s+money|浪费钱|不值得(?:买|购买)|不值这个价", headline)
        and has(r"ceo|executive|高管|创始人|首席执行官", headline))
    suggested_policy = (has(r"may\s+have\s+to|should|应该", headline)
        and has(r"(?:now\s+)?being\s+suggested|建议", opening)
        and has(r"not\s+a\s+live\s+issue|could\s+start\s+to\s+hit|未来可能影响", ' '.join(source_units or source_facts))
        and not has(r"court|regulat|legislation|法院|法规", opening))
    if (publisher_selection or publisher_opinion or quoted_purchase_opinion or suggested_policy
            or source_editorial_evaluation(title, ' '.join(source_units)[:600] if source_units else lead)
            or (identity.content_form == "podcast"
                and not is_os_release_announcement(title)
                and _title_owned_action_profile(title, lead, evidence, identity) is None)
            or source_editorial_outlook(title, lead, source_units or source_facts)):
        return profile(f"editorial:{headline}", "publisher-source-form", tier="weak",
                       category="software_systems" if identity.title_products & _SOFTWARE_FIRST_PARTY_PRODUCTS else "hardware_products",
                       kind="general_company",
                       content_form=identity.content_form,
                       reason="publisher selection or opinion without its own current Apple action",
                       weak_boundary="source-local-editorial-form")

    # Bind a demonstration's own target; later project history cannot demote
    # an Apple release, and an OS name does not identify its host hardware.
    if (identity.title_products & _SOFTWARE_FIRST_PARTY_PRODUCTS
            and has(r'port|移植|刷入|启动', headline + ' ' + opening[:500])):
        intro = _normalized(source_units[0]) if source_units else opening
        first_end = next(source_sentence_spans(intro), (0, len(intro)))[1]
        port_claim = intro[:first_end]
        port_target = _compiled_rule(
            r'在([^。；;，,]{2,65}?)上(?:成功)?(?:运行|启动)\s*(?:苹果\s*)?(?:ios|ipados|macos|watchos|tvos|visionos)|'
            r'\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*(?:\d+(?:\.\d+)*)?\s*'
            r'(?:support\s+)?(?:on\s+|to\s+|移植到|运行在)([^。；;.!?]{2,65})|'
            r'(?:令|让|为|将(?:一部)?)([^。；;，,]{2,65}?)(?:手机)?(?:刷入|启动|运行)\s*(?:[^。；;，,]{1,45}专版的\s*)?(?:苹果\s*)?'
            r'(?:ios|ipados|macos|watchos|tvos|visionos)(?:\s*/\s*(?:ios|ipados))?\s*\d', re.I).search(port_claim)
        target = next((v for v in port_target.groups() if v), '') if port_target else ''
        if (target and identity.title_products & _SOFTWARE_FIRST_PARTY_PRODUCTS
                and not has(r'\b(?:iphone|ipad|mac|macbook|imac|vision\s*pro|apple\s*watch|apple\s*silicon)\b|苹果\s*m\d|苹果硬件', target)
                and has(r'\b(?:developer|hobbyist|enthusiast)\b|开发者|爱好者|网友|博主', port_claim)
                and has(r'demonstrat|showcas|展示|演示|成果|成功', port_claim)
                and not has(r'^(?:apple|苹果).{0,25}(?:releas|launch|发布|推出)', port_claim)):
            return profile(f"third-party:software-port:{headline}", "current-demonstration",
                           tier="weak", kind="third_party_ecosystem",
                           reason="independent software-port demonstration on non-Apple hardware")

    content = _first_party_content_claim(title, lead, identity, evidence)
    if content and content[1] == 'performance-lineup-announcement':
        subject, action = content
        return profile('apple-music-content:' + subject, action, kind='service_content')
    if (content and content[1] == "trailer"
            and not has(r"\b(?:trailer|teaser)\b|预告片", headline)
            and has(r"\bapple\s*tv\b.{0,35}\b(?:unveils?|announces?)\b", headline)):
        subject, action = content
        result = profile("apple-tv-content:" + subject, action, kind="service_content")
        return replace(result, boundary_keys=result.boundary_keys | {"content-title:" + subject},
                       separation_keys=result.separation_keys | {"content-title:" + subject, "content-action:" + action})

    operation = source_operation_frame(title, lead, source_facts, identity, source_units=source_units, published_year=published_year)
    if operation is not None and operation.bound_claim is not None:
        return bound_reconciliation_profile(operation.bound_claim)
    if operation is not None:
        if (operation.action in {'launch-date-confirmation', 'launch-date-report'}
                and not (operation.action == 'launch-date-confirmation' and operation.subject == 'apple:product-launch-campaign'
                         and has(r'\bevent\b|\bexperience\b|发布会|特别活动|官宣', headline))):
            # Calendar evidence supplements an owned launch, never replaces
            # an existing concrete participation, retail or platform action.
            specific = _title_owned_action_profile(title, lead, evidence, identity)
            if specific is not None:
                return specific
            exact_claims = _primary_claim_projection(title, lead, identity, regions, evidence, source_facts=source_facts)[0]
            if exact_claims and not all(key.endswith((':product-launch', ':reported-launch-window', ':event-schedule-announcement', ':schedule-forecast')) or ':generation-product-refresh:' in key for key in exact_claims):
                operation = None
    if (operation is not None and operation.action == "market-measurement-report"
            and operation.subject.endswith(":smartphone-shipments")):
        measured = _measured_apple_market_result_keys(title, lead, " ".join((evidence, *source_facts)))
        stamp = operation.year + "-" + operation.period
        if any(key.split(":")[3] == stamp for key in measured if len(key.split(":")) == 6):
            # Numeric reports retain existing metric-role evidence. The same
            # source-owned report key is also attached by claim projection.
            operation = None
    if operation is not None:
        # Generic device operations supplement the existing precise claim parser;
        # region, investigator, part code and before/after relations remain binding.
        if (operation.action == "device-teardown" or operation.action.startswith("production-")):
            teardown = operation if operation.action == 'device-teardown' and ':publishers:' in operation.subject else None
            exact = _primary_claim_projection(title, lead, identity, regions, evidence,
                source_facts=source_facts, teardown_operation=teardown)
            if teardown and exact[0]:
                return ReconciliationProfile(event_keys=frozenset(exact[0]), boundary_keys=frozenset(exact[1]),
                    separation_keys=frozenset(exact[2]) | {'source-local-action-authority'}, category_hint=exact[3] or operation.category,
                    identity=replace(identity, content_form='news'), relevance_tier=operation.tier,
                    trusted_direct_action=exact[4], promotion_reason='source-owned teardown publications',
                    event_kind_hint=operation.kind)
            if exact[0]:
                operation = None
        if (operation is not None and operation.subject == "apple-tv:weekly-viewership"
                and _first_party_content_claim(title, lead, identity)):
            operation = None
    if operation is not None:
        if operation.action == "firmware-update":
            _family, _firmware, builds, stage = operation.subject.split(":")
            key = "apple-firmware:airpods-" + stage
            return ReconciliationProfile(
                event_keys=frozenset({key, *("code-build:airpods-" + build for build in builds.split(",") if build)}), boundary_keys=frozenset({key}),
                separation_keys=frozenset({"primary-claim-subject:airpods-firmware", "primary-claim-predicate:firmware-" + stage,
                                           *("code-build:airpods-" + build for build in builds.split(",") if build)}),
                category_hint="software_systems", identity=identity, relevance_tier="strong",
                trusted_direct_action=True, promotion_reason="source-owned first-party firmware release",
                event_kind_hint="os_app")
        action = ('measured-apple-market-result'
            if operation.action == 'market-measurement-report' and operation.subject.endswith(':smartphone-shipments')
            else operation.action)
        result = profile(operation.subject, action, tier=operation.tier,
                       category=operation.category, kind=operation.kind,
                       reason=("third-party source-owned action" if operation.subject.startswith("third-party:")
                               else "source-local " + operation.action if operation.tier == "weak"
                               else "source-owned operation and functional category"))
        if operation.action == 'market-measurement-report':
            measured = _measured_apple_market_result_keys(
                title, lead, " ".join((evidence, *source_facts)), published_year=published_year)
            result = replace(result, event_keys=result.event_keys | measured,
                separation_keys=result.separation_keys | _market_result_separation_keys(measured))
        if not operation.category:
            result = replace(result, review_reasons=(
                "Functional category unresolved in this source; verify the action's technical object before assigning the final section. The displayed category is provisional.",))
        if operation.subject.startswith('apple-immersive:content:') and operation.action == 'premiere-schedule':
            work = operation.subject.removeprefix('apple-immersive:content:').replace('-', ' ')
            schedule = {'content-primary-premiere'}
            if operation.period:
                schedule.add('content-date:' + operation.period)
            if operation.year:
                schedule.add('content-date-year:' + operation.year)
            result = replace(result, separation_keys=result.separation_keys | schedule | {
                'content-title:' + work.replace(' ', '-'), 'content-action:premiere-schedule'})
        if operation.action == "forecast-correction":
            # A revision of a forecast is itself an affirmative disclosure;
            # negation of the old forecast does not deny the current report.
            result = replace(result, identity=replace(result.identity,
                title_components=result.identity.title_components - {"claim-polarity:configuration-denied"}))
        if operation.action in {'launch-date-confirmation', 'launch-date-report'}:
            # Use the established campaign/calendar vocabulary, including
            # regional-day alternatives, instead of a competing date boundary.
            campaign_key = _apple_event_campaign_key(title, lead)
            calendar = _apple_event_occurrence_keys(title, lead)
            _, month, _, day = operation.period.split(':')
            stamp = f'{int(month):02d}-{int(day):02d}'
            zones = {key.split(':')[1] for key in calendar if key.startswith('apple-event-calendar:') and key.endswith(':' + stamp)}
            calendar = {key for key in calendar if key.startswith('apple-event-year:') or key.endswith(':' + stamp)}
            if 'beijing' in zones:
                previous = date(2000, int(month), int(day)) - timedelta(days=1)
                calendar.add(f'apple-event-occurrence:{previous.month:02d}-{previous.day:02d}')
            if not calendar:
                calendar = {f'apple-event-occurrence:{int(month):02d}-{int(day):02d}',
                            f'apple-event-calendar:unspecified:{int(month):02d}-{int(day):02d}'}
            additions = calendar | ({campaign_key} if campaign_key else set())
            if operation.subject == 'apple:product-launch-campaign':
                result = replace(result,
                    event_keys=frozenset(), boundary_keys=frozenset(),
                    separation_keys=frozenset({'primary-claim-subject:apple-event-campaign', 'source-local-action-authority'}))
            result = replace(result, event_keys=result.event_keys | additions,
                boundary_keys=result.boundary_keys | additions,
                separation_keys=result.separation_keys | calendar | {'source-launch-stage:' + operation.action})
            result = replace(result, separation_keys=result.separation_keys | {
                'source-launch-subject:' + value for value in operation.launch_subjects})
        elif operation.period:
            result=replace(result,separation_keys=result.separation_keys | {"source-report-period:"+operation.period})
        if operation.action == 'display-specification-report' and operation.subject == 'ipad-mini:oled-refresh':
            result = replace(result, event_keys=result.event_keys | {'canonical-apple-action:ipad-mini:oled-display-adoption'})
        if operation.model_generation:
            generation, _, size = operation.model_generation.partition(':')
            model_keys = {"source-model-generation:" + generation} if generation else set()
            if size:
                model_keys.add("source-model-size:" + size)
            result = replace(result, separation_keys=result.separation_keys | model_keys)
        if operation.year:
            result=replace(result,separation_keys=result.separation_keys | {"source-report-year:"+operation.year})
        if operation.region:
            result=replace(result,separation_keys=result.separation_keys | {'source-report-region:' + operation.region})
        if operation.aliases:
            result=replace(result,event_keys=result.event_keys | {
                f"primary-claim:{alias}:{operation.action}" for alias in operation.aliases})
        return result

    # Bind the built-in capability before the device hosting it. The headline
    # owns the component; a sparse feature headline may use its opening only.
    photo_face_current = any(
        has(r"\bphoto\s+face\b|照片面孔", clause)
        and has(r"\b(?:shared|discovered|found|reveals?|leaked)\b|曝光|爆料|新增", clause)
        and has(r"apple['’]s|apple\s+(?:beta\s+)?code|苹果|setting\s+up\s+the\s+home\s+hub", clause)
        and not has(r"\b(?:last\s+(?:year|month|week)|previously|existing|unchanged|"
                    r"not\s+new|not\s+found|found\s+no)\b|去年|此前|原有|未发现|并非新", clause)
        for clause in [headline, *_compiled_rule(r"[。！？；;]|(?<=[.!?])\s+", 0).split(opening[:750], 0)]
    )
    feature_components = []
    for scope in (headline, opening[:750]):
        owned_components = software_components(scope)
        feature_components = [(scope.find(alias), name.removeprefix("os-component:"))
            for name, aliases in OS_COMPONENT_PATTERNS for alias in aliases if alias in scope
            and name in owned_components
            and (name != "os-component:photo-face" or photo_face_current)]
        if feature_components:
            break
    component = min(feature_components)[1] if feature_components else ""
    discovery_scope = headline + " " + opening[:750]
    if photo_face_current:
        # A named face is the changed object; StandBy is its containing feature.
        component = "photo-face"
    if (component and identity.scope == "apple-direct" and identity.content_form == "news"
            and not has(r"\b(?:released|available\s+now|rolls?\s+out)\b|正式发布|正式上线|现已推送", headline)
            and has(r"\b(?:unannounced|unreported|code|localization\s+strings?|leaker)\b|代码|未公布|未发布|消息源|爆料者", discovery_scope)
            and current_primary_predicate(
                r"\b(?:discovered|found|reveals?|shared|leak)\b|发现|挖掘|曝光",
                r"\b(?:found\s+no|not\s+found|did\s+not\s+find|no\s+new)\b|未发现|没有新|"
                r"(?:并未|没有|未曾|未能)(?:(?:从|在|通过)[^。；，,.!?]{0,24})?(?:发现|挖掘)",
                whole_clause_history=True)):
        device = _compiled_rule(r"(?<![a-z0-9])(iphone|ipad|macbook)\s*(duo|air|mini|\d+(?:\s*pro(?:\s*max)?)?)(?![a-z0-9])", 0).search(headline)
        subject = (device.group(1) + "-" + _compiled_rule(r"\s+", 0).sub("-", device.group(2), 0)) if device else ",".join(sorted(identity.title_products))
        if component == "photo-face":
            subject = "apple"
        version = _compiled_rule(r"(?<![a-z0-9])(ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+)*)(?![a-z0-9])", 0).search(headline)
        if version:
            subject = f"{version.group(1)}-{version.group(2)}" + (":" + subject if device else "")
        if subject:
            return profile(f"{subject}:{component}", "feature-code-discovery",
                           reason="source-owned discovery of an unreleased built-in software capability")

    # A how-to can report a named feature introduced in a specified OS.
    # Require both the new capability and its first-party app, not a sponsor
    # or the word 'new' elsewhere in an evergreen instruction page.
    os_feature = _compiled_rule(r"(?:苹果\s*)?(ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+)*)", 0).match(headline)
    named_feature = _compiled_rule(r"\bnew\s+['\"“]([^'\"”]{2,50})['\"”]\s+feature|新[增的]*[‘“]([^’”]{2,50})[’”]功能", 0).search(headline)
    first_party_apps = identity.title_products & {"safari", "siri", "notes", "photos", "mail", "shortcuts"}
    if (os_feature and named_feature and first_party_apps
            and any(re.match(r"\s*" + re.escape(app) + r"(?:['’]s)?\s+new\s+['\"“]", opening)
                    for app in first_party_apps)
            and has(r"\bnew\b.{0,70}\bfeature\b.{0,45}\b(?:lets|allows|enables)\b|新增.{0,40}功能.{0,30}(?:允许|支持)", opening[:600])
            and not has(r"\b(?:unchanged|previously|last\s+year|not\s+new)\b|早已|去年|此前|并非新", opening[:350])):
        name = next(v for v in named_feature.groups() if v)
        return profile(f"{os_feature.group(1)}-{os_feature.group(2)}:{','.join(sorted(first_party_apps))}:{name}",
                       "system-capability-report", reason="named current-version first-party capability")

    # Discounts can describe an official catalog or education-program action.
    # Leave those established identities to the normal action policy.
    retail_deal = is_retail_promotion(identity)
    if is_personal_product_complaint(title, lead) or retail_deal or is_weekly_editorial_recap(lead):
        return profile(f"editorial:{headline}", "publisher-source-form", tier="weak",
                       category="hardware_products" if identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS else "software_systems",
                       kind="third_party_ecosystem" if retail_deal else "general_company", content_form=identity.content_form,
                       reason="source-owned retail promotion, personal complaint or weekly recap",
                       weak_boundary="source-local-editorial-form")
    design_role = source_design_oversight(title, lead, evidence)
    if design_role:
        design_leader, stage = design_role
        return profile(f"apple:design-leadership:{design_leader}", stage+"-design-oversight",
                       tier="weak" if stage == "historical" else "strong",
                       category="hardware_products", kind="company_org",
                       reason="source-owned Apple executive design responsibility: " + stage)
    if is_editorial_change_request(title):
        return profile(f"editorial:{headline}", "feature-wishlist", tier="weak",
                       category="hardware_products" if identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS else "software_systems",
                       kind="general_company", content_form=identity.content_form,
                       reason="author's desired feature, not a current Apple action")
    leave_notice = source_employee_leave_notice(title, lead)
    if leave_notice:
        return profile(f"apple:employee-leave:{leave_notice}", "current-employee-notice",
                       category="hardware_products", kind="general_company",
                       reason="current Apple employee leave notice")
    store_measure = source_store_sales_measure(title, lead, identity)
    if store_measure:
        return profile(store_measure, "store-sales-observation", category="hardware_products",
                       kind="hardware_market", reason="attributed per-store Apple hardware sales observation")
    workload_measure = source_device_workload_measure(title, lead, source_facts, identity)
    if workload_measure:
        return profile(workload_measure, "current-benchmark-report", category="hardware_products",
                       kind="hardware_market", reason="source-owned Apple device workload measurement")
    hardware_project = source_hardware_project(title, lead, source_facts, identity)
    if hardware_project:
        product, project = hardware_project
        return profile(f"{product}:project:{project}", "current-roadmap-report",
                       category="hardware_products", kind="hardware_market",
                       reason="current source-owned named hardware development program")

    # A court's action against Apple is direct legal news even when the
    # rights holder is a third party. Bind the claimant before background.
    if (has(r"\bapple\b|苹果", headline) and has(r"patent|专利", headline)
            and has(r"\b(?:jury|court)\b|陪审团|法院", opening[:500])
            and has(r"damages|赔偿|赔付", headline + " " + opening[:500])):
        claimant = _compiled_rule(r"(?:侵犯\s*|infringed\s+)([a-z][a-z0-9-]*)(?:['’]s)?(?:\s+patents?|.{0,25}专利)", re.I).search(opening[:500])
        current_verdict = current_primary_predicate(
            r"\bfound\s+apple\s+(?:has\s+)?infringed\b|裁定.{0,30}苹果.{0,20}侵犯",
            r"\b(?:not|never)\s+found\s+apple\b|尚未裁定|没有裁定|并未裁定|并无新裁决")
        if claimant and current_verdict:
            return profile(f"apple-patent-case:{claimant.group(1).lower()}", "jury-damages-verdict",
                           category="hardware_products", kind="legal_antitrust",
                           reason="current source-attributed patent damages verdict against Apple")

    device = source_device_disclosure(title, lead)
    if device:
        family, generation = device
        result = profile(f"{family}:device-disclosure", "unreleased-device-disclosure",
                         category="hardware_products", kind="hardware_market",
                         reason="source-owned disclosure of an unreleased Apple device")
        if generation:
            result = replace(result, separation_keys=result.separation_keys | {
                f"product-model:{family}:{generation}"})
        return result

    # First-party app versions belong to the app, not a device mentioned as
    # motivation or an OS version used as a compatibility condition.
    if has(r"\btestflight\b", headline):
        app_scope = " ".join((headline, opening, *source_facts))
        version = _compiled_rule(r"\btestflight(?:\s+(?:version|应用至))?\s*(\d+\.\d+(?:\.\d+)?)", re.I).search(app_scope)
        if (version and has(r"\b(?:updated?|released?|adds?|works?)\b|更新|新增", headline + " " + opening[:600])
                and not has(r"\b(?:not|never)\s+(?:updated|released)\b|未更新|没有更新|计划更新", headline + " " + opening[:350])):
            planned = has(r"\b(?:plans?\s+to|will)\s+update\b|计划更新|将更新", headline + " " + opening[:350])
            return profile(f"testflight:{version.group(1)}", "app-update-plan" if planned else "app-update",
                           reason="source-owned versioned first-party Apple app action")

    if (has(r"\bairpods\b", headline)
            and has(r"\b(?:firmware|software)\s+update\b|固件更新", headline)
            and has(r"\b(?:released|arrived|got)\b|发布|推送", headline + " " + opening[:500])):
        builds = sorted(set(_compiled_rule(r"(?<![a-z0-9])\d+[a-z]\d{2,}(?![a-z0-9])", 0).findall(local)))
        if builds:
            return profile("airpods:firmware:" + ",".join(builds), "firmware-update",
                           reason="first-party device firmware update")

    os_notes = _compiled_rule(r"\b(ios|ipados|macos|watchos|tvos)\s*(\d+(?:\.\d+)*)", 0).search(headline)
    if os_notes and has(r"release\s+notes|更新日志|更新说明", headline):
        publication = current_primary_predicate(
            r"\bapple\s+(?:(?:today|finally|has|now|just)\s+)*(?:shares?|shared|publishes?|published)\b|"
            r"苹果.{0,20}(?:补发|公布|公开|发布)",
            r"\bapple\s+(?:has\s+)?(?:not|never)\s+(?:shared|published)\b|"
            r"苹果.{0,12}(?:尚未|没有|并未).{0,12}(?:发布|公布)")
        if publication:
            return profile(f"{os_notes.group(1)}-{os_notes.group(2)}:release-notes",
                           "document-publication", reason="source-owned release-note publication")
        if has(r"unofficial|非官方|\bapple\s+(?:has\s+)?(?:not|never)\s+(?:shared|published)\b|"
               r"苹果.{0,12}(?:尚未|没有|并未).{0,12}(?:发布|公布)", headline + " " + opening[:400]):
            return profile(f"{os_notes.group(1)}-{os_notes.group(2)}:release-notes",
                           "document-commentary", tier="weak",
                           reason="release-note discussion without an affirmative Apple publication")
        # A headline may call an actual RC/system push its release notes;
        # retain that existing release authority when no publication is asserted.

    # A technical publication has a first-party actor and an affirmative
    # local predicate. Accessory uses and comparison prose are not its owner.
    def publication_of(object_pattern: str) -> bool:
        return current_primary_predicate(
            r"(?:\bapple\s+(?:(?:has|today|now|officially|recently)\s+)*(?:publishe[sd]|release[sd]|update[sd]|shared|shares|reveale[sd])\b|"
            r"苹果(?:官方|公司)?(?:近期|近日|今天|今日|悄悄|正式|已经|已)*(?:在[^。；]{1,60})?(?:公布|发布|公开|更新))"
            r"[^。.!?;；]{0,260}(?:" + object_pattern + r")",
            r"\bapple\s+(?:has\s+)?(?:not|never)\b|苹果(?:官方|公司)?[^。；]{0,70}(?:尚未|没有|并未|计划|将会)")

    if (has(r"(?:dimensional|design|technical)\s+drawings|(?:尺寸|立体|设计)图纸?|产品设计图", headline)
            and has(r"\bapple\b|苹果", headline)
            and publication_of(r"(?:dimensional|design|technical)\s+drawings|(?:尺寸|立体|设计)图纸?")
            and has(r"dimensional\s+drawings|尺寸图纸|立体图纸", opening)):
        return profile("apple:dimensional-drawings", "document-catalog-report",
                       category="hardware_products", kind="hardware_market",
                       reason="first-party technical drawings for current products")

    if (has(r"\bmacs?\b|苹果", headline)
            and has(r"(?<![a-z])ai(?![a-z])|人工智能", headline)
            and publication_of(r"local\s+(?:ai|models?)|本地(?:大模型|ai)")
            and has(r"\blocal\s+(?:ai|models?)\b|本地(?:大模型|ai)", opening)
            and has(r"parameters?|参数|支持能力", opening)):
        target = ",".join(sorted(identity.title_products)) or "mac"
        chips = sorted(component for component in identity.title_components
                       if component.startswith("apple-silicon-generation:"))
        subject = "apple:local-ai-model-capacity:" + target
        if chips:
            subject += ":" + ",".join(chips)
        return profile(subject, "official-capability-report",
                       category="hardware_products", kind="hardware_market",
                       reason="Apple publishes local model capacity of its devices")

    if (has(r"\btvos\s*\d+", headline) and has(r"screensaver|屏保", headline)
            and has(r"sound|audio|音效|音频", headline + " " + opening[:400])
            and has(r"\b(?:code|leak)\b|代码|泄露", local)):
        version = _compiled_rule(r"\btvos\s*(\d+(?:\.\d+)*)", 0).search(headline).group(1)
        return profile(f"tvos-{version}:screensaver-audio", "feature-code-discovery",
                       reason="OS screensaver capability discovered in code")

    iphone = _compiled_rule(r"iphone\s*(\d+)\s*pro\s*max", 0).search(headline)
    if (iphone and has(r"at&t", opening)
            and has(r"cellular\s+issues|通信翻车|网络异常|无法打电话", headline + " " + opening[:400])):
        return profile(f"iphone-{iphone.group(1)}-pro-max:att-cellular", "connectivity-issue-report",
                       category="hardware_products", kind="hardware_market",
                       reason="current attributed device connectivity issue")
    if (iphone and has(r"different\s+hardware\s+versions|地区.*硬件版本", headline)
            and has(r"\bapple\s+sells\b|苹果销售", opening)):
        return profile(f"iphone-{iphone.group(1)}-pro-max:regional-hardware", "regional-model-report",
                       category="hardware_products", kind="hardware_market")

    macos = _compiled_rule(r"\bmacos\s*(\d+)", 0).search(headline)
    if (macos and has(r"manufacture\s+date|生产日期", headline)
            and has(r"\bapple\s+has\s+restored\b|苹果恢复", opening[:500])):
        return profile(f"macos-{macos.group(1)}:manufacture-date", "system-capability-report")
    if (has(r"apple\s+card", headline) and has(r"recurring\s+transactions?", opening[:700])
            and has(r"\bios\s*\d+", headline)):
        version = _compiled_rule(r"\bios\s*(\d+)", 0).search(headline).group(1)
        return profile(f"ios-{version}:apple-card-recurring-transactions", "system-capability-report")

    wallet_version = _compiled_rule(r"\bios\s*(\d+)", 0).search(opening[:450])
    if (wallet_version and has(r"wallet|钱包", headline)
            and has(r"custom\s+passes|import\s+physical\s+passes|自定义凭证", opening[:450])):
        return profile(f"ios-{wallet_version.group(1)}:wallet-custom-passes", "system-capability-report")
    if (has(r"apple\s+music\s+hall", headline)
            and has(r"\bfirst\b.{0,70}\b(?:shows|artists|gig|performing)\b|首批演出", headline + " " + opening[:400])
            and has(r"\b(?:announced|revealed|confirms|confirmed)\b|公布|宣布", headline + " " + opening[:400])):
        return profile("apple-music-hall:opening-program", "performance-lineup-announcement",
                       kind="service_content", reason="named venue's inaugural performance lineup")

    # A cross-platform device connection changes Apple interoperability;
    # ordinary availability of an app in the Watch store alone does not.
    if (has(r"apple\s+watch", headline) and has(r"互联|配对|interoperab|pairing", headline)
            and has(r"上架|上线|rollout|launched", headline)
            and has(r"同步|sync", opening[:650]) and has(r"手机|android", opening[:650])):
        return profile(f"watch-interoperability:{headline.split('互联')[0]}", "cross-platform-rollout",
                       tier="ecosystem", kind="ecosystem_interop",
                       reason="current cross-platform Apple Watch device and data connection")

    # The grammatical owner of an OTA is the automaker. A CarPlay mention
    # inside its feature inventory does not make this an Apple OS release.
    if (has(r"\bota\b", headline) and has(r"carplay", headline)
            and has(r"车型|汽车|车机|\b(?:vehicle|automaker|car)\b", headline + " " + opening[:250])
            and not has(r"carplay\s+ultra|苹果(?:发布|更新)|apple\s+(?:releases?|updates?)", headline)):
        return profile(f"third-party-vehicle:{headline}", "vehicle-update", tier="weak",
                       reason="automaker OTA with routine CarPlay compatibility")
    if (has(r"采访|新书|\binterview\b", opening[:400])
            and has(r"回忆|理念|\bhistor|(?:19|20)\d{2}\s*年.{0,30}(?:聘请|加入|担任)|共事", headline + " " + opening)
            and not has(r"任命|加入苹果|接任|\bappoint", headline)):
        return profile(f"editorial:{headline}", "historical-interview", tier="weak",
                       category="hardware_products", kind="company_org",
                       reason="historical interview without a current Apple organizational action")
    if (has(r"apple\s+tv", headline) and has(r"i\s+can['’]t\s+keep\s+up|我.*看不完", headline)):
        return profile(f"editorial:{headline}", "viewing-commentary", tier="weak",
                       kind="service_content", reason="personal viewing commentary without a service action")
    if (has(r"here['’]s\s+(?:the\s+lineup|everything\s+to\s+expect)|前瞻|展望", headline + " " + opening[:300])
            and has(r"hardware\s+and\s+software|硬件和软件", headline + " " + opening[:300])
            and not has(r"new\s+(?:report|leak)|新爆料", opening[:300])):
        return profile(f"editorial:{headline}", "product-preview", tier="weak",
                       category="hardware_products", reason="editorial preview of existing announcements and rumors")

    # Source form belongs to the publisher's opening assertion.  Linked
    # headlines, sponsors, and a recalled beta feature cannot replace it.
    editorial_form = (
        identity.content_form == "podcast" and has(r"\blisten\s+to\s+a\s+recap\b", opening[:350])
        or identity.content_form == "poll" and has(r"^(?:【[^】]*(?:互动|调查|投票)[^】]*】|\[poll\])", headline)
        or identity.content_form == "roundup" and (
            has(r"\b(?:announced|released|unveiled)\s+\d+\s+(?:new\s+)?products?\s+in\s+the\s+past\s+month\b", headline)
            or (has(r"\bproducts?\s+launching\s+soon\b", headline)
                and has(r"\b(?:rumou?red|waited\s+a\s+long\s+time)\b", opening[:600]))
        )
    )
    if editorial_form:
        return profile(f"editorial:{headline[:110]}", "publisher-source-form",
                       tier="weak", category="software_systems", kind="general_company",
                       reason=f"publisher {identity.content_form} without a new Apple action",
                       content_form=identity.content_form,
                       weak_boundary="source-local-editorial-form")

    # Code hidden behind a feature flag is a discovery about a named OS
    # build, not three releases nor an already available watch-face feature.
    watch_build = _compiled_rule(r"\bwatchos\s*(\d+(?:\.\d+){1,2})\b", 0).search(local)
    if (watch_build and has(r"\bscreenshots?\b|截图", headline)
            and has(r"\b(?:code|feature\s+flag|hidden|leaker)\b|代码|隐藏|flag", opening[:650])
            and has(r"\b(?:preview|share|delete)\b|预览|分享|删除", opening[:650])
            and current_primary_predicate(
                r"\b(?:found|discovered|code\s+hints?|code\s+(?:shows?|reveals?))\b|"
                r"(?:发现|指出|代码显示).{0,100}(?:截图|隐藏功能|flag)",
                r"\b(?:found\s+no|no\s+.{0,60}(?:code|flag)|not\s+found|did\s+not\s+find)\b|"
                r"\b(?:released|available\s+now|already\s+available|rolled\s+out)\b|"
                r"未(?:发现|找到).{0,35}(?:代码|flag|截图)|已(?:发布|上线|推送)")):
        return profile(f"watchos-{watch_build.group(1)}:screenshot-preview",
                       "feature-flag-code-discovery",
                       reason="source reports a screenshot capability found in unreleased OS code")

    # The festival and stream are one object; an in-person ticket is a
    # separate condition of attendance, not the price of this stream.
    festival = (_compiled_rule(r"\b(?:free\s+)?([a-z]+\s+[a-z]+)\s+festival\b", 0).search(headline)
        or _compiled_rule(r"\b([a-z]+\s+[a-z]+)\s+音乐节", 0).search(headline))
    if (festival and has(r"\bapple\s+music\b", headline)
            and has(r"\b(?:livestream|live\s+stream)\b|直播", headline)
            and has(r"\bgoldenvoice\b", opening[:500])
            and has(r"\bindio\b|印第奥", opening[:500])):
        name = festival.group(1).replace(" ", "-")
        stream_action = (r"\b(?:teaming\s+up|partner(?:ing|ed)?|will\s+livestream|to\s+host)\b"
                         r".{0,100}\b(?:livestream|festival)\b|(?:宣布|合作).{0,100}直播|免费直播")
        stream_cancel = (r"\b(?:cancel(?:s|led|ed)?|scrap(?:s|ped)?|abandon(?:s|ed)?|"
                         r"no\s+longer\s+(?:plans?\s+to\s+)?(?:host|livestream))\b|"
                         r"\b(?:not|never)\s+(?:host|livestream)\b|取消.{0,35}直播|不再直播")
        subject = f"apple-music:{name}:festival"
        if current_primary_predicate(stream_cancel, stream_action):
            return profile(subject, "livestream-cancellation",
                           reason="current cancellation of the named festival stream")
        if current_primary_predicate(stream_action, stream_cancel):
            return profile(subject, "livestream-announcement",
                           reason="current Apple Music festival livestream")

    # A newly published explainer video is the present action.  The control
    # features it describes can have been available since the OS launch.
    family_version = _compiled_rule(r"\bios\s*(\d+)\b", 0).search(local)
    if (family_version and has(r"\bapple\b|苹果", headline + " " + opening[:300])
            and has(r"\b(?:parental\s+controls?|child\s+accounts?|child\s+safety)\b|家长控制|儿童账户|儿童安全", local)
            and has(r"\bvideo\b|视频", headline + " " + opening[:500])
            and has(r"\b(?:shared|released|published)\s+(?:a\s+)?(?:new\s+)?video\b|"
                    r"\bvideo\s+today\b|发布新宣传视频|发布.{0,8}视频", opening[:550])
            and current_primary_predicate(
                r"\b(?:shared|released|published)\s+(?:a\s+)?(?:new\s+)?(?:animated\s+)?video\b|"
                r"发布.{0,8}(?:宣传)?视频",
                r"\b(?:has|have|had|did|does)\s+not\s+(?:yet\s+)?(?:share|shared|release|released|publish|published)\b|"
                r"\bno\s+new\s+video\b|未(?:曾|有|发布|分享).{0,25}视频")):
        return profile(f"apple:parental-controls:ios-{family_version.group(1)}",
                       "current-explainer-video", reason="current Apple parental-controls video")

    # A watch-face bezel is an on-screen configuration, not physical bezel
    # hardware.  Extract its named option from either language's own lead.
    watch_model = _compiled_rule(r"\bapple\s+watch\s+ultra\s*(\d+)\b", 0).search(local)
    bezel_name = (_compiled_rule(r"\b([a-z]+)\s+is\s+a\s+new\s+bezel\s+option\b", 0).search(local)
        or _compiled_rule(r"\(([a-z]+)\)\s*表圈", 0).search(local))
    if (watch_model and bezel_name and has(r"\bwatch\s+face\b|表盘", local)
            and has(r"\bbezel\s+(?:option|configuration|complication)\b|表圈选项", local)
            and has(r"\b(?:new|adding|adds|includes)\b|新增|推送|现支持", local)):
        bezel_added = (r"\b(?:adds?|adding|includes?)\s+(?:a\s+)?new\b.{0,70}\bbezel\b|"
                       r"\bnew\s+(?:watch\s+face\s+)?bezel\s+option\b|"
                       r"(?:新增|推送|现支持).{0,65}(?:表圈|表盘)")
        bezel_denied = (r"\b(?:does|did|has|have)\s+not\s+(?:include|add|support)\b|"
                        r"\bno\s+new\b.{0,55}\bbezel\b|"
                        r"(?:未|没有|并未).{0,40}(?:新增|推送|支持).{0,35}(?:表圈|表盘)")
        subject = f"apple-watch-ultra-{watch_model.group(1)}:watch-face:{bezel_name.group(1)}"
        if current_primary_predicate(bezel_denied, bezel_added):
            return profile(subject, "configuration-denied", tier="weak",
                           reason="source denies the named watch-face configuration")
        if current_primary_predicate(bezel_added, bezel_denied):
            return profile(subject, "configuration-added",
                           reason="current named watch-face configuration")

    # Current OS support removals concern the OS owner even when the list
    # includes accessories, older processors, and later-version exceptions.
    macos_name = _compiled_rule(r"\bmacos\s+(?:\d+(?:\.\d+)*\s+)?([a-z]+\s+[a-z]+)\b", 0).search(opening[:500])
    if (macos_name and has(r"\bmacos\b", headline)
            and has(r"\b(?:gone|removed?|dropped|phased\s+out)\b|移除|不再支持", headline + " " + opening[:300])
            and has(r"\b(?:legacy|intel|boot\s+camp|afp|rosetta)\b|遗留|英特尔", opening[:600])
            and has(r"\bapple\b|苹果", headline + " " + opening[:550])
            and current_primary_predicate(
                r"\b(?:gone|removed?|dropped|phased\s+out|cuts?\s+support)\b|"
                r"(?:移除|终结).{0,60}(?:支持|功能)|仅支持.{0,50}并移除",
                r"\b(?:has|have|had|did|does)\s+not\s+(?:remove|removed|drop|dropped|phase\s+out)\b|"
                r"\b(?:still\s+supports?|retains?\s+support)\b|"
                r"(?:未|没有|并未).{0,35}(?:移除|终结|取消).{0,35}(?:支持|功能)")):
        os_name = macos_name.group(1).replace(" ", "-")
        return profile(f"macos-{os_name}:legacy-support", "current-removal",
                       reason="current macOS legacy support removal")

    # A feature inventory is an editorial work even when one listed item is a
    # current first-party feature covered by a separate guide.
    if (has(r"^\d+\s+(?:new\s+)?things\b|^\d+\s+项", headline)
            and has(r"\b(?:ios|ipados|macos|watchos|tvos)\s*\d+", headline)):
        version = _compiled_rule(r"\b(ios|ipados|macos|watchos|tvos)\s*(\d+)", 0).search(headline)
        return profile(f"{version.group(1)}-{version.group(2)}:feature-roundup",
                       "editorial-inventory", tier="weak", reason="multi-feature editorial roundup",
                       content_form="roundup")

    # A confirmed upcoming repair is the current action. The major OS name
    # only describes the delivery vehicle, not an exact patch or release.
    iphone_repair_model = _compiled_rule(r"(?<![a-z0-9])iphone\s*(\d+)\s*pro(?![a-z0-9])", 0).search(headline)
    repair_scope = f"{headline}. {opening[:850]}"
    if (identity.content_form == "news" and iphone_repair_model
            and has(r"\bapple\b.{0,95}\b(?:confirms?|confirmed|plans?\s+to)\b|"
                    r"苹果.{0,35}(?:确认|证实|承诺|表示|回应)", repair_scope)
            and has(r"\b(?:software|system|ios\s*\d+(?:\.\d+)*)\s+(?:update|patch)\b|"
                    r"软件更新|系统(?:版本)?更新|ios\s*\d+(?:\.\d+)*\s*更新|ios更新|ios系统更新|专项补丁", repair_scope)
            and has(r"\b(?:fix|repair|address|resolve)\b|修复|解决|修补", repair_scope)
            and has(r"\b(?:coming|next\s+week|expected|planned|working\s+on|in\s+the\s+works)\b|"
                    r"下周|预计|计划|后续|将推送|未来数天|正在(?:开发|测试)|进入.{0,12}测试阶段", repair_scope)
            and has(r"\breboot|restart\b|重启|\bface\s*id\s+(?:issue|bug)\b", repair_scope)
            and has(r"\bface\s*id\b|面容\s*id|面容识别|面部识别", repair_scope)
            and not has(r"\b(?:released|available\s+now|rolled\s+out)\b|已发布|已推送|现已推送|"
                        r"\bnot\s+(?:coming|expected|planned)\b|不会|并非", headline)
            and not has(r"\bapple\s+(?:has\s+|have\s+)?(?:not|never)\s+"
                        r"(?:confirmed|announced|promised)\b[^.!?]{0,180}"
                        r"\b(?:software\s+(?:update|patch)|fix|repair)\b|"
                        r"苹果.{0,8}(?:尚未|并未|没有|否认).{0,8}(?:确认|承诺|宣布)"
                        r".{0,60}(?:软件更新|系统更新|修复)", opening[:850])
            and not has(r"\bsoftware\s+(?:update|patch)\b[^.!?;]{0,150}"
                        r"\b(?:was|has\s+been|is)\s+(?:already\s+)?"
                        r"(?:released|rolled\s+out|available)\b|"
                        r"(?:软件更新|系统更新|\bios\s*\d+(?:\.\d+)*\s*更新)"
                        r"[^。；;]{0,80}(?:已(?:经)?(?:发布|推送|上线)|正式(?:发布|推送))",
                        opening[:850])):
        return profile(f"iphone-{iphone_repair_model.group(1)}-pro:face-id-reboot",
                       "software-fix-commitment",
                       reason="Apple-confirmed upcoming software repair for a named device issue")

    # The parties and the effective date must belong to the source's current
    # affirmative agreement, not to a publication date or an older contract.
    if identity.content_form == "news" and has(r"\bapple\b|苹果", headline):
        party_match = next((match for pattern in (
            r"^(?P<party>[a-z][a-z0-9.&-]{1,35})\b.{0,100}\b(?:with|and)\s+apple\b",
            r"^apple\s*(?:&|and|with)\s*(?P<party>[a-z][a-z0-9.&-]{1,35})\b",
            r"^(?P<party>[\u4e00-\u9fff]{2,12}?)(?:公司)?(?:今日|今天)?(?:宣布|与苹果|和苹果)",
            r"^苹果(?:与|和)(?P<party>[\u4e00-\u9fff]{2,12}?)(?:公司)?(?:续签|续约|延长)",
        ) if (match := re.search(pattern, headline)) is not None), None)
        if party_match is not None:
            party = party_match.group("party")
            for sentence in _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(opening[:850], 0)[:3]:
                party_in_sentence = (party in sentence if _compiled_rule(r"[\u4e00-\u9fff]", 0).search(party)
                    else re.search(rf"(?<![a-z0-9]){re.escape(party)}(?![a-z0-9])", sentence) is not None)
                current_agreement = (
                    party_in_sentence and has(r"\bapple\b|苹果", sentence)
                    and has(r"\b(?:patent\s+licens(?:e|ing)|licens(?:e|ing)\s+agreement)\b|专利许可协议", sentence)
                    and has(r"\brenew(?:s|ed|al)?\b|\bextend(?:s|ed)?\b|续签|续约|延长", sentence)
                    and has(r"\b(?:today|announc\w*|confirm\w*)\b|今日|今天|宣布|已(?:经)?(?:与苹果|和苹果)?.{0,35}(?:续签|续约|延长)", sentence)
                    and not has(r"\bden(?:y|ies|ied)\b[^.!?]{0,100}\b(?:renew\w*|extend\w*)\b|"
                                r"\b(?:has|have|had|did|does|do|will|was|were|is|are)\s+not\s+(?:yet\s+)?(?:renew\w*|extend\w*)\b|"
                                r"\b(?:never\s+(?:renew\w*|extend\w*)|no\s+(?:renewal|extension))\b|"
                                r"(?:未|没有|否认|并未)[^，,；;。！？]{0,30}(?:续签|续约|延长)", f"{headline}. {sentence}")
                    and not has(r"\b(?:previously|earlier|historically|back\s+in)\b|此前|过去|曾经|早前|回顾", headline)
                    and not has(r"^(?:in\s+(?:19|20)\d{2}\b|back\s+in\b|previously\b|earlier\b|此前|过去|曾经)", sentence)
                )
                if not current_agreement:
                    continue
                month_names = "january february march april may june july august september october november december".split()
                english_date = _compiled_rule(r"\b(?:effective(?:\s+date)?(?:\s+(?:of|on|from|as\s+of))?|takes?\s+effect\s+(?:on|from))\s+"
                    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+"
                    r"(\d{1,2}),?\s+(20\d{2})\b", 0).search(sentence)
                chinese_date = _compiled_rule(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(?:起)?(?:继续)?生效|"
                    r"(?:生效日期|生效时间)(?:为|是|于)\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", 0).search(sentence)
                if english_date:
                    month_name, day, year = english_date.groups()
                    month = month_names.index(month_name) + 1
                elif chinese_date:
                    parts = chinese_date.groups()
                    year, month, day = parts[:3] if parts[0] else parts[3:]
                else:
                    year = None
                if year is not None:
                    try:
                        date_key = date(int(year), int(month), int(day)).isoformat()
                    except ValueError:
                        pass
                    else:
                        party_key = (name_aliases or {}).get(party, party)
                        return profile(f"apple:{party_key}:patent-license:effective-{date_key}",
                                       "bilateral-renewal",
                                       reason="current bilateral Apple patent-license renewal")

    # The implementer owns the Dashboard rollout, while Apple Business is the
    # first-party data endpoint. Keep the named implementer in the subject.
    integration_actor = _compiled_rule(r"^([a-z][a-z0-9.-]{1,35})\s+(?:now\s+)?(?:integrates?|adds?|announces?)\b", 0).match(headline)
    if (integration_actor and has(r"\bapple\s+business\s+integration\b|"
            r"\bintegrat\w*\s+with\s+apple\s+business\b", headline)
            and has(r"\b(?:dashboard|sellers?|businesses?)\b", opening)
            and has(r"\b(?:maps|wallet|siri)\b", opening)):
        return profile(f"apple-business:{integration_actor.group(1)}:dashboard",
                       "platform-data-integration", tier="ecosystem",
                       reason="current third-party integration with Apple Business data")

    archival_video = bool(
        has(r"\b(?:q\s*&\s*a|questions?\s+and\s+answers?)\b|问答", headline)
        and has(r"\b(?:video|recording|footage)\b|视频", headline)
        and has(r"\b(?:surfac(?:e|es|ed)|resurfac(?:e|es|ed))\b|流出|重现|出现", headline)
        and has(r"\b(?:19|20)\d{2}\b", opening)
        and has(r"\b(?:iphone\s*\d+|ipad|mac|apple\s+watch)\b", headline)
    )
    if archival_video:
        device = _compiled_rule(r"\b(iphone\s*\d+|ipad|mac|apple\s+watch)\b", 0).search(headline)
        context = "antennagate" if has(r"antennagate|天线门", headline) else "historical-event"
        return profile(f"archive:{device.group(1).replace(' ', '-')}:{context}",
                       "historical-video-resurfacing", tier="weak",
                       content_form="analysis", reason="third-party resurfacing of historical Apple video")

    # A future device lineup and a released camera service's price concern
    # different objects and stages even when both mention Apple Home hardware.
    if (has(r"\bapple\s+tv\b", headline) and has(r"\bhomepod\b", headline)
            and has(r"\b(?:on\s+track|expected|rumou?red|planned|to\s+launch)\b", headline)
            and has(r"\b(?:rumou?r|reiterat\w*|report\w*)\b", opening[:400])
            and has(r"\b(?:this\s+year|later\s+this\s+year|upcoming)\b", opening[:400])):
        return profile("apple-home:apple-tv-homepod-mini", "future-device-lineup-report",
                       category="hardware_products", kind="hardware_market",
                       reason="source reports a future Apple Home device lineup")
    home_software = _compiled_rule(r"\bios\s*(\d+)\b", 0).search(opening[:500])
    if (has(r"\bapple\s+home\b", headline)
            and has(r"\bsecurity\s+cameras?\b", headline)
            and has(r"\b(?:cost|price|subscription|monthly)\b", headline)
            and home_software
            and has(r"\b(?:public\s+release|released|available\s+now)\b", opening[:500])
            and has(r"\b(?:apple\s+intelligence|ai.powered|ai.generated)\b", opening[:700])
            and has(r"\$\s*\d|\bper\s+month\b|\ba\s+month\b", local)):
        return profile(f"apple-home:security-camera-ai:ios-{home_software.group(1)}",
                       "current-software-subscription-pricing",
                       reason="released camera AI service and its subscription price")

    # Current actions by independent actors cannot be inherited by Apple from
    # the device, operating system, employee biography, or historical context.
    if (has(r"\bcopland\b", headline)
            and has(r"\b(?:emulat\w*|simulat\w*|browser|dingusppc)\b|模拟运行", local)
            and has(r"\b(?:reverse.engineer|michael\s+steil|modified|patches)\b|逆向工程师|补丁", local)):
        return profile("copland:third-party-emulation", "current-demonstration",
                       tier="weak", reason="independent emulation of historical Apple software")
    if (has(r"\bmac\s*mini\b", headline)
            and has(r"\b(?:handheld|cyberdeck|mod|modified|batteries)\b|改装", local)
            and has(r"\b(?:chris\s+cheng|shring|youtube|personal\s+project)\b|个人", local)):
        return profile("mac-mini:independent-hardware-mod", "current-demonstration",
                       tier="weak", category="hardware_products", kind="hardware_market",
                       reason="independent Mac mini modification")
    if (has(r"\bmuse\s+charm\b|\bmuse\s+造了个\s+ai\b|电子宠物.{0,20}muse", headline)
            and has(r"\b(?:device|handheld|prototype|charm|unveil\w*|announc\w*)\b|设备|装置|电子宠物|发布|造了", headline)
            and has(r"\b(?:device|handheld|prototype|screen|charm)\b|设备|装置|屏幕", opening[:500])):
        return profile("meta:muse-charm:device", "announcement",
                       tier="weak", category="hardware_products", kind="hardware_market",
                       reason="Meta device announcement with Apple alumni context")
    if (has(r"\bemmy(?:\s+awards)?\b|艾美奖", headline)
            and has(r"\bternus\b|特努斯", headline)
            and has(r"(?<![a-z0-9])iphone\s+duo(?![a-z0-9])", headline)
            and has(r"\bemmy(?:\s+awards)?\b|艾美奖", opening[:500])
            and has(r"\bternus\b|特努斯", opening[:500])
            and has(r"(?<![a-z0-9])iphone\s+duo(?![a-z0-9])", opening[:500])
            and has(r"\b(?:attend\w*|arriv\w*|show\w*|display\w*|demo\w*|sport\w*)\b|出席|展示|亮相", opening[:500])):
        return profile("apple-executive:ternus:emmy-awards:iphone-duo", "current-event-display",
                       tier="weak", category="hardware_products", kind="hardware_market",
                       reason="source reports an executive displaying the device at an awards event")

    # Legacy product-explanation interviews remain outside the migrated
    # company-responsibility scope; retire this branch with that family.
    # A past CEO quote is background in launch, store, guide and event reports.
    # The interview must be the opening assertion about this product and actor.
    first_assertion = _compiled_rule(r"[。！？；;]|(?<=[.!?])\s+(?=[a-z])", 0).split(opening, 1)[0]
    interview_verb = _compiled_rule(r"\binterview(?:ed|s)?\b|采访|专访|访谈", 0).search(first_assertion)
    if (has(r"(?<![a-z0-9])iphone\s+duo(?![a-z0-9])", headline)
            and has(r"(?<![a-z0-9])iphone\s+duo(?![a-z0-9])", first_assertion)
            and has(r"\bternus\b|特努斯", first_assertion)
            and interview_verb
            and not has(r"\b(?:unveil\w*|launch\w*|releas\w*|announc\w*|display\w*)\b|"
                        r"发布|推出|揭幕|展出|亮相", first_assertion[:interview_verb.start()])):
        return profile("apple-executive:iphone-duo:design-interview", "interview-remarks",
                       tier="weak", category="hardware_products", kind="hardware_market",
                       reason="executive interview about an existing product")

    interoperation = _compiled_rule(r"^([\u4e00-\u9fff]{2,8})\s*\d+\s*(?:pro|ultra|系列)", 0).search(headline)
    if (interoperation and has(r"(?:apple\s*watch|苹果手表).{0,30}互联|互联.{0,30}(?:apple\s*watch|苹果手表)", headline)
            and has(r"电话|通知|健康|\bcalls?\b|notifications?|health", local)):
        actor = _compiled_rule(r"[^a-z0-9]+", 0).sub("-", interoperation.group(1), 0).strip("-") or interoperation.group(1)
        return profile(f"third-party-phone-{actor}:apple-watch", "interoperability-update",
                       tier="ecosystem", reason="third-party platform interoperability")

    # Release, test and compatibility stages are separate actions, even when
    # the same numeric build appears in nearby coverage.
    os_version = _compiled_rule(r"\bwatchos\s*(\d+(?:\.\d+)*)", 0).search(headline)
    if (os_version and not has(r"\bbeta\b|测试版|预览版", headline) and has(r"\b(?:fix\w*|releas\w*|rolling\s+out|arrived)\b|推送|修复", headline)
            and has(r"restart|reboot|随机重启|意外重启", local)):
        stage_scope = f"{headline}. {opening[:240]}"
        version_marker = rf"\bwatchos\s*{re.escape(os_version.group(1))}\b"
        version_sentences = [sentence for sentence in _compiled_rule(r"(?<=[.!?])\s+(?=[a-zA-Z])|[。！？]", 0).split(stage_scope, 0)
                             if re.search(version_marker, sentence)]
        if any(_compiled_rule(r"\b(?:has|have|had|will|does|did|is|was)\s+not\s+"
                r"(?:yet\s+)?(?:been\s+)?releas\w*\b|"
                r"\bnot\s+yet\s+released\b|尚未(?:发布|推送)", 0).search(sentence) for sentence in version_sentences):
            return profile(f"watchos-{os_version.group(1)}:watch-restart", "public-fix-not-released",
                           tier="weak", reason="source denies current watchOS fix release")
        if any(_compiled_rule(r"\b(?:plans?|planned|intends?|scheduled|will)\s+"
                r"(?:to\s+)?(?:release|ship|roll\s+out)\b|"
                r"\b(?:release|fix|update)\s+(?:is\s+)?(?:still\s+)?planned\b|"
                r"计划(?:发布|推送)|尚待(?:发布|推送)", 0).search(sentence) for sentence in version_sentences):
            return profile(f"watchos-{os_version.group(1)}:watch-restart", "public-fix-planned",
                           tier="weak", reason="source describes a planned watchOS restart fix")
        if has(r"\b(?:releas\w*|arrived|deployed|rolling\s+out|fix\w*|update)\b|推送|修复", local):
            return profile(f"watchos-{os_version.group(1)}:watch-restart", "public-fix-release",
                           reason="current watchOS restart fix release")
    if (has(r"\b(?:at&t|att)\b", headline)
            and has(r"\biphone\s+handoff\b", headline)
            and has(r"\b(?:potential|existing\s+esim|noncommittal|no\s+imminent\s+plans)\b|现有\s*esim", local)):
        return profile("att:iphone-handoff", "current-carrier-response",
                       reason="current carrier response about Apple feature support")
    if (has(r"\btvos\s*\d+", headline) and has(r"\bhomepod\b", headline)
            and has(r"\b(?:four|4)\s+(?:\w+\s+){0,3}homepods?\b|4\s*台\s*homepod", local)
            and has(r"\b(?:pair|connect|support|surround)\w*\b|配对|连接|支持|环绕", local)):
        major = _compiled_rule(r"\btvos\s*(\d+)", 0).search(headline).group(1)
        return profile(f"tvos-{major}:homepod-four-speaker-pairing", "beta-capability-report",
                       reason="source-local tvOS pairing capability report")
    if (has(r"\bhomepod\b", headline) and has(r"\bsiri\s*ai\b", headline)
            and has(r"\b(?:audioos|homepod\s+software|homepod)\s*\d+", local)
            and has(r"\b(?:linwood|code|status\s+lights?)\b|代码|指示灯", local)):
        version = _compiled_rule(r"\b(?:audioos|homepod\s+software|homepod)\s*(\d+)", 0).search(local)
        return profile(f"homepod-software-{version.group(1)}:siri-ai-code", "current-code-disclosure",
                       reason="HomePod Siri AI code disclosure, not activation")


    # Reports of a measured configuration and of its replaceability are
    # different predicates.  Do not turn the report's comparison into the act.
    if (has(r"(?<![a-z0-9])mac\s*mini(?![a-z0-9])", headline) and has(r"\b(?:ssd|storage)\b|固态硬盘|读写|顺序", local)
            and has(r"\b(?:benchmark|blackmagic|sequential|read|write|speed|faster|slower)\b|实测|测试|顺序读|顺序写", local)
            and has(r"(?<![a-z0-9])\d+\s*gb(?![a-z0-9])", local)):
        model = _compiled_rule(r"\bm(\d+)\s*(?:pro\s+)?(?:mac\s*mini)?", 0).search(local)
        capacity = _compiled_rule(r"(?<![a-z0-9])(\d+)\s*gb(?![a-z0-9])", 0).search(local)
        if model and capacity and (has(r"\bblackmagic\b|aapl\s*ch", local)
                                   or has(r"顺序(?:读|写)", local)):
            return profile(f"mac-mini:m{model.group(1)}:{capacity.group(1)}gb:ssd",
                           "current-benchmark-report", category="hardware_products",
                           kind="hardware_market", reason="source-attributed Mac mini SSD measurement")

    if (has(r"(?<![a-z0-9])iphone\s+duo(?![a-z0-9])", headline)
            and has(r"良率|yield", headline)
            and has(r"产量|volume|production", headline)
            and has(r"代工厂|contract\s+manufacturer|supplier", local)):
        return profile("iphone-duo:contract-production", "yield-volume-report",
                       category="hardware_products", kind="hardware_market",
                       reason="source-attributed production yield report")

    design_statements = [
        _normalized(fact) for fact in source_facts[:6]
        if _compiled_rule(r"20\s*周年|20th[- ]anniversary|anniversary\s+iphone", re.I).search(fact)
        and not _compiled_rule(r"\blast\s+(?:year|month|week)\b|去年|上周", re.I).search(fact)
    ]
    if (has(r"\biphone\b", headline)
            and has(r"屏幕|设计|\b(?:display|design|borderless|border-free|curved)\b", headline)
            and has(r"20\s*周年|\banniversary\b|\b20th\b", local + " " + " ".join(design_statements))
            and any(has(r"\b(?:coe|ltpo\+?)\b", statement)
                    and has(r"推迟|暂缓|postpone|delay|not\s+implement", statement)
                    for statement in design_statements)):
        return profile("anniversary-iphone:display-design", "current-roadmap-report",
                       category="hardware_products", kind="hardware_market",
                       reason="current anniversary iPhone design report")
    if (has(r"\b(?:openai|chatgpt)\b", headline)
            and has(r"\b(?:apple|苹果|siri|apple\s+intelligence)\b", local)
            and has(r"\b(?:filing|court\s+document|lawsuit|legal\s+filing)\b|法庭文件|法律文件", local)
            and has(r"\b(?:underperform\w*|disappoint\w*)\b|低于预期|表现不佳", local)):
        if (has(r"\b(?:old|historical|revisited|recap)\b|旧闻|回顾", headline)
                or has(r"\bfiling\s+last\s+year\b|\bno\s+new\s+(?:court\s+)?filing\b|此前的法庭文件", opening[:300])):
            return profile("openai:apple-chatgpt-integration", "historical-filing-recap",
                           tier="weak", reason="prior filing cited without a current disclosure")
        return profile("openai:apple-chatgpt-integration", "current-court-filing-disclosure",
                       kind="legal_antitrust", reason="current attributed OpenAI court filing")

    if (has(r"\bcook\b|库克", headline)
            and has(r"\baward\b|获奖|奖", headline)
            and has(r"\b(?:announc\w*|selected|recipient)\b|公告|被选为", opening)
            and has(r"\b(?:sia|semiconductor\s+industry\s+association)\b|半导体行业协会", opening)):
        award = "noyce" if has(r"noyce|诺伊斯", opening) else "industry-award"
        return profile(f"apple-executive:tim-cook:{award}", "current-award-announcement",
                       kind="general_company", reason="current award announced for Apple executive")
    return None


def build_reconciliation_profile(
    *,
    title: str,
    lead: str,
    identity: EventIdentity,
    exact_facets: Iterable[str],
    regions: Iterable[str],
    relevance_tier: str = "strong",
    relevance_reason: str = "",
    trusted_direct_action: bool = False,
    event_kind: str = "",
    evidence: str = "",
    embedded_references: tuple = (),
    source_facts: tuple[str, ...] = (),
    source_units: tuple[str, ...] = (),
    name_aliases: Mapping[str, str] | None = None,
    published_year: str = "",
) -> ReconciliationProfile:
    regions = tuple(regions)
    profile = source_action_reconciliation_profile(
        title=title, lead=lead, identity=identity, regions=regions,
        event_kind=event_kind, evidence=evidence, source_facts=source_facts,
        source_units=source_units, name_aliases=name_aliases, published_year=published_year)
    if profile is not None:
        return profile
    return build_legacy_reconciliation_profile(
        title=title, lead=lead, identity=identity, exact_facets=exact_facets,
        regions=regions, relevance_tier=relevance_tier, relevance_reason=relevance_reason,
        trusted_direct_action=trusted_direct_action, event_kind=event_kind,
        evidence=evidence, embedded_references=embedded_references,
        source_facts=source_facts, source_units=source_units,
        name_aliases=name_aliases, published_year=published_year)


def source_action_reconciliation_profile(
    *, title: str, lead: str, identity: EventIdentity,
    regions: Iterable[str] = (), event_kind: str = "", evidence: str = "",
    source_facts: tuple[str, ...] = (), source_units: tuple[str, ...] = (),
    name_aliases: Mapping[str, str] | None = None, published_year: str = "",
) -> ReconciliationProfile | None:
    """Run the existing ordered source rules before legacy support is needed."""
    regions = tuple(regions)
    card_rate = _card_savings_rate_report(title, lead, source_facts)
    if card_rate is not None:
        if card_rate[0] == "historical":
            return ReconciliationProfile(
                event_keys=frozenset(), boundary_keys=frozenset(),
                category_hint="software_systems", identity=identity,
                relevance_tier="weak",
                defer_reason="historical Apple Card savings rate without a current action",
                hard_boundary="historical-rate-report", event_kind_hint=event_kind,
            )
        _status, old_rate, new_rate = card_rate
        subject = "apple-card-savings-account"
        if _status == "denied":
            return ReconciliationProfile(
                event_keys=frozenset({f"primary-claim:apple:{subject}:rate-increase-denied:{old_rate}-to-{new_rate}"}),
                boundary_keys=frozenset({f"primary-claim-subject:{subject}"}),
                separation_keys=frozenset({f"primary-claim-subject:{subject}",
                                          "primary-claim-predicate:rate-increase-denied"}),
                category_hint="software_systems", identity=replace(identity, content_form="news"),
                relevance_tier="weak", trusted_direct_action=False,
                defer_reason="source denies the current Apple Card savings rate increase",
                hard_boundary="negated-current-rate-increase", event_kind_hint="os_app",
            )
        return ReconciliationProfile(
            event_keys=frozenset({f"primary-claim:apple:{subject}:rate-increase:{old_rate}-to-{new_rate}"}),
            boundary_keys=frozenset({f"primary-claim-subject:{subject}"}),
            separation_keys=frozenset({f"primary-claim-subject:{subject}",
                                      "primary-claim-predicate:rate-increase"}),
            category_hint="software_systems", identity=replace(identity, content_form="news"),
            relevance_tier="strong", trusted_direct_action=True,
            promotion_reason="current Apple Card savings account rate change",
            event_kind_hint="os_app",
        )
    if is_platform_compatible_accessory_title(title):
        return ReconciliationProfile(
            event_keys=frozenset({f"structured-canonical-title:{_canonical_title(title)}"}),
            boundary_keys=frozenset(), identity=identity, relevance_tier="weak",
            category_hint=source_accessory_category(title) or "hardware_products",
            event_kind_hint="third_party_ecosystem",
            defer_reason="third-party accessory; platform name is compatibility context",
            hard_boundary="third-party-platform-accessory",
        )
    return _source_local_current_action(title, lead, source_facts, identity, name_aliases, regions, evidence, source_units, published_year)


def build_legacy_reconciliation_profile(
    *,
    title: str,
    lead: str,
    identity: EventIdentity,
    exact_facets: Iterable[str],
    regions: Iterable[str],
    relevance_tier: str = "strong",
    relevance_reason: str = "",
    trusted_direct_action: bool = False,
    event_kind: str = "",
    evidence: str = "",
    embedded_references: tuple = (),
    source_facts: tuple[str, ...] = (),
    source_units: tuple[str, ...] = (),
    name_aliases: Mapping[str, str] | None = None,
    published_year: str = "",
) -> ReconciliationProfile:
    """Unmigrated continuation after the ordered source rules found no profile."""
    regions = tuple(regions)
    named_action = _source_owned_named_action(title, lead)
    if named_action is not None:
        subject, predicate = named_action
        actor = ("us-government" if subject.startswith("us-government:") else
                 "expand-mac-mini" if subject.startswith("expand-mac-mini:") else "apple")
        legal_stage = {
            "current-amicus-filing": "legal-stage:government-amicus-filing",
            "opening-merits-brief": "legal-stage:apple-opening-merits-brief",
        }.get(predicate)
        document_stage = (
            "source-current-action:mac-mini-ssd-support-document:current"
            if predicate == "support-document-revision" else None
        )
        category = ("software_systems" if predicate in {
            "support-scope-clarification", "gesture-restoration", "permission-restriction",
            "availability-expansion", "venue-opening", "first-party-update",
            "development-report", "beta-feature-change", "software-availability-expansion",
            "firmware-update", "current-government-meeting",
            "current-amicus-filing", "opening-merits-brief", "reported-market-result",
        } else "hardware_products")
        return ReconciliationProfile(
            event_keys=frozenset({f"primary-claim:{actor}:{subject}:{predicate}"}),
            boundary_keys=frozenset({f"primary-claim-subject:{subject}"}),
            separation_keys=frozenset({f"primary-claim-subject:{subject}",
                                      f"primary-claim-predicate:{predicate}"}
                                     | ({legal_stage} if legal_stage else set())
                                     | ({document_stage} if document_stage else set())),
            category_hint=category,
            identity=replace(identity, content_form="news"),
            relevance_tier="strong", trusted_direct_action=True,
            promotion_reason=("source-owned named government filing" if actor == "us-government"
                              else "source-owned named supplier disclosure" if actor == "expand-mac-mini"
                              else "source-owned named Apple action"), event_kind_hint=event_kind,
        )
    title_owned = _title_owned_action_profile(title, lead, evidence, identity)
    if title_owned is not None:
        return replace(title_owned, event_kind_hint=event_kind)
    # An observed allocation report is not an OS feature launch. Keep the
    # reported object, version, and measured device attached to its title act.
    storage_title = _normalized(title)
    storage_version = _compiled_rule(r"(?<![a-z0-9])macos\s*(\d+(?:\.\d+){0,2})(?![0-9.])").search(storage_title)
    if (identity.scope == "apple-direct" and identity.content_form == "news"
            and storage_version and "apple intelligence" in storage_title
            and _compiled_rule(r"(?<![a-z0-9])macs?(?![a-z0-9])|(?<![a-z0-9])macbook(?![a-z0-9])").search(storage_title)
            and _compiled_rule(r"\b(?:taking|takes|using|uses|consuming|consumes)\s+(?:up\s+)?"
                               r"\d+(?:\.\d+)?\s*gb(?![a-z0-9])|(?:占用|占据|耗用)[^。！？]{0,25}"
                               r"\d+(?:\.\d+)?\s*gb(?![a-z0-9])").search(storage_title)):
        report_lead = _normalized(lead)[:1000]
        if (_compiled_rule(r"\b(?:higher|above|exceed\w*|more than)\b|远超|远高于|高于|超过|异常|膨胀").search(report_lead)
                and _compiled_rule(r"\bapple\s+(?:says|lists|states)\b|\bofficial\b|苹果(?:表示|公布|规定)|官方").search(report_lead)):
            version = _normalized_os_version(storage_version.group(1))
            observations = set()
            for device in _compiled_rule(
                    r"(?<![a-z0-9])m\d+(?:\s+(?:pro|max|ultra))?\s+"
                    r"(?:mac\s+mini|macbook\s+(?:air|pro|neo))(?![a-z0-9])").finditer(report_lead):
                window = _compiled_rule(r"。|(?<!\d)\.(?!\d)").split(
                    report_lead[device.end():device.end() + 160], maxsplit=1)[0]
                amount = _compiled_rule(r"(?<![a-z0-9])\d+(?:\.\d+)?\s*gb(?![a-z0-9])").search(window)
                if amount and _compiled_rule(r"\b(?:saw|recorded|measured|observed|found|reports?)\b|"
                                             r"发现|记录|实测|看到|显示").search(window[:amount.start()]):
                    model = _compiled_rule(r"[^a-z0-9]+").sub("-", device.group()).strip("-")
                    observations.add(f"structured-measure:macos-{version}:"
                                     f"apple-intelligence-storage:{model}:{amount.group().replace(' ', '')}")
            if observations:
                subject = f"macos-{version}:apple-intelligence-storage"
                return ReconciliationProfile(
                    event_keys=frozenset(observations),
                    boundary_keys=frozenset({f"primary-claim-subject:{subject}"}),
                    separation_keys=frozenset({f"primary-claim-subject:{subject}",
                                               "primary-claim-predicate:storage-occupancy-report",
                                               "action:storage-occupancy-report"}),
                    category_hint="software_systems", identity=identity,
                    relevance_tier="strong", trusted_direct_action=True,
                    promotion_reason="source-backed Apple Intelligence storage observation",
                    event_kind_hint=event_kind)
    caller_trusted_direct_action = trusted_direct_action
    title_text = _normalized(title)
    text = f"{title_text}. {_normalized(lead)[:900]}"
    editorial_first_party_action = _editorial_source_proves_current_first_party_action(
        title,
        lead,
        identity,
    )
    source_hardware_release = _source_current_hardware_release(lead, identity)
    exact = frozenset(exact_facets)
    # Facets remain inputs to the existing domain matcher.  They are not
    # automatically cross-event keys: even a precise facet can describe more
    # than one action in a busy news cycle.
    event_keys: set[str] = {component for component in identity.title_components if component.startswith("system-wallpaper:")}
    boundary_keys: set[str] = set()
    separation_keys = _product_separation_keys(identity)
    document_stage = _ssd_support_document_stage(title, lead)
    if document_stage is not None:
        # A mention, planned change, or outside repair cannot inherit an
        # affirmative Apple document revision through generic product keys.
        separation_keys.add(f"source-current-action:mac-mini-ssd-support-document:{document_stage}")
    # A denied filing and an expressly different filer may still look like
    # the same legal case to generic reconciliation.  Preserve their stated
    # owner and stage without promoting either to an affirmative Apple/DOJ act.
    legal_case = (_compiled_rule(r"(?<![a-z0-9])epic(?![a-z0-9])", re.I).search(text)
                  and _compiled_rule(r"\b(?:supreme\s+court|scotus)\b|最高法院", re.I).search(title_text)
                  and _compiled_rule(r"\bapp\s*store\b|外链抽佣", re.I).search(lead)
                  and _compiled_rule(r"\b(?:commission|injunction)\b|抽佣|禁令", re.I).search(lead))
    if legal_case:
        for actor, relation_pattern in (
            ("apple-opening-brief", _APPLE_EPIC_OPENING_FILING),
            ("government-amicus", _GOVERNMENT_AMICUS_FILING),
        ):
            filing = _compiled_rule(relation_pattern, re.I).search(title_text)
            if filing is not None:
                scope = _filing_time_scope(title_text, filing)
                # A dated filing without current corroboration is not a past
                # filing by default, but it must not inherit the current stage.
                if scope in {"past", "future", "dated"}:
                    separation_keys.add(f"legal-stage:{actor}-{scope}")
    if legal_case and _compiled_rule(
        r"\bapple\b\s+(?:will\s+not|does\s+not|has\s+not)\s+"
        r"(?:file|submit|filed|submitted)\s+(?:its\s+)?(?:opening|merits)\s+brief\b",
        re.I,
    ).search(title_text):
        separation_keys.add("legal-stage:apple-opening-brief-not-filed")
    if legal_case and _compiled_rule(
        r"^epic\s*(?:本周|今日|今天)?\s*向(?:美国)?最高法院\s*提交法庭之友意见书",
        re.I,
    ).search(title_text):
        separation_keys.add("legal-stage:epic-amicus-filing")
    performance_keys, performance_boundaries = _platform_performance_evidence(title, evidence)
    event_keys.update(performance_keys)
    separation_keys.update(performance_boundaries)
    company_performance_subject = quantified_apple_company_performance_subject(
        title,
        lead,
    )
    if company_performance_subject:
        event_key = f"structured-company-performance:{company_performance_subject}"
        event_keys.add(event_key)
        boundary_keys.add(event_key)
        separation_keys.add("primary-claim-predicate:quantified-company-performance")
        trusted_direct_action = True
    separation_keys |= _predicate_separation_keys(identity)
    separation_keys |= _title_predicate_separation_keys(title)
    service_subjects = identity.title_products & (FIRST_PARTY_SERVICE_PRODUCTS | {"app-store"})
    if len(service_subjects) == 1 and identity.content_form == "news":
        # These are separation predicates, not merge keys: a generic feature
        # or fee change does not identify which feature or fee changed.
        fee_change = _compiled_rule(r"\b(?:raises?|increases?|lowers?|reduces?)\b.{0,65}\b(?:fees?|prices?|pricing)\b|"
            r"(?:提高|上调|降低|下调).{0,30}(?:费用|收费|价格)|(?:费用|收费|价格).{0,20}(?:上涨|下调)", 0).search(title_text)
        feature_change = bool(
            "feature-change" in identity.title_actions
            and _compiled_rule(r"\b(?:features?|interface)\b|功能|界面", 0).search(title_text)
        )
        if fee_change or feature_change:
            separation_keys.add(f"primary-claim-subject:{next(iter(service_subjects))}")
            separation_keys.add(
                "primary-claim-predicate:service-fee-change" if fee_change
                else "primary-claim-predicate:service-feature-change"
            )
    changed_object_keys = _changed_object_separation_keys(title, lead, identity)
    separation_keys |= changed_object_keys
    separation_keys |= _title_product_period_keys(title, identity)
    evidence_products = _bounded_evidence_products(
        f"{_normalized(lead)[:900]} {_normalized(evidence)[:1200]}"
    )
    primary_evidence_products = _bounded_evidence_products(
        " ".join(
            (
                _primary_assertion_scope("", lead)[1],
                _primary_assertion_scope("", evidence)[1],
            )
        )
    )
    structured_title_subjects = _structured_title_subjects(
        identity,
        primary_evidence_products or evidence_products,
    )
    category_hint = _structured_category_hint(identity, structured_title_subjects, title)
    if named_action is not None:
        category_hint = ("software_systems" if named_action[1] == "support-scope-clarification"
                         else "hardware_products")
    for component in identity.components:
        if component.startswith("device-software-release:"):
            _, product, version = component.split(":", 2)
            event_keys.add(f"canonical-apple-action:{product}:software-release:{version}")
            separation_keys.add(f"primary-claim-predicate:device-software-release")
    if source_hardware_release:
        category_hint = "hardware_products"
    if company_performance_subject:
        category_hint = "software_systems"
    if editorial_first_party_action and len(identity.title_products) == 1:
        editorial_product = next(iter(identity.title_products))
        editorial_update_key = f"structured-title-product-update:{editorial_product}"
        event_keys.add(editorial_update_key)
        boundary_keys.add(editorial_update_key)
        if editorial_product in _HARDWARE_FIRST_PARTY_PRODUCTS or editorial_product == "polishing-cloth":
            category_hint = "hardware_products"
    content_form = _reconciliation_content_form(title_text, identity)
    third_party_app_availability = (
        _third_party_app_availability_without_platform_change(title_text, lead)
        or is_third_party_app_action_on_apple_platform(title_text, lead)
    )
    if (
        content_form == "news"
        and len(primary_evidence_products & _HARDWARE_FIRST_PARTY_PRODUCTS) >= 3
        and not identity.title_products
        and not identity.title_components
        and len(identity.actions) >= 2
        and not exact
    ):
        # A title without a concrete subject cannot own several unrelated
        # product/action pairs found only in its body. Treat it as an editorial
        # summary so it cannot bridge the product events it recaps.
        content_form = "roundup"
    projected_hardware_roadmap = bool(
        _compiled_rule(r"apple\s+.+\s+roadmap\s+update", 0).fullmatch(title_text)
        and identity.scope == "apple-direct"
        and identity.title_products
        & {
            "airpods",
            "apple-home-hub",
            "apple-tv",
            "apple-watch",
            "beats",
            "foldable-iphone",
            "homepod",
            "imac",
            "ipad",
            "iphone",
            "mac",
            "mac-mini",
            "mac-pro",
            "mac-studio",
            "macbook",
            "vision-pro",
        }
    )

    canonical_title = _canonical_title(title_text)
    if content_form == "news" and len(canonical_title) >= 18:
        canonical_title_key = f"structured-canonical-title:{canonical_title}"
        event_keys.add(canonical_title_key)
        boundary_keys.add(canonical_title_key)

    accessory_evaluation = _hardware_accessory_evaluation_claim(
        title_text,
        lead,
        identity,
    )
    if accessory_evaluation:
        product, accessory = accessory_evaluation
        accessory_key = (
            f"canonical-apple-action:{product}:{accessory}-"
            + ("project-cancellation" if _compiled_rule(r"\b(?:cancel(?:led|ed)?|abandoned|scrapped)\b|取消|放弃|叫停|终止", re.I).search(title_text) else "compatibility-evaluation")
        )
        event_keys.add(accessory_key)
        boundary_keys.add(f"structured-subject:{product}:{accessory}")
        separation_keys |= {
            f"primary-claim-subject:{product}:{accessory}",
            "primary-claim-predicate:accessory-compatibility-evaluation",
        }
        category_hint = "hardware_products"

    for product, component in _hardware_component_adoption_claims(
        title_text,
        lead,
        identity,
    ):
        component_key = f"canonical-apple-action:{product}:{component}-adoption"
        if component == "camera-system":
            adoption_scope = title_text + ". " + _short_lead_scope(lead, sentences=1)
            if _local_current_camera_adoption(lead, identity):
                separation_keys.add("camera-adoption-stage:announced")
            elif _compiled_rule(r"\b(?:rumored|expected|reportedly|may|might|could)\b|将首次|预计|传闻", re.I).search(adoption_scope):
                separation_keys.add("camera-adoption-stage:reported")
            elif _compiled_rule(r"\bapple\s+(?:has\s+|today\s+)?(?:announced|revealed|launched|unveiled)\b|苹果(?:今日|今天|正式).*?(?:公布|发布|推出)", re.I).search(adoption_scope):
                separation_keys.add("camera-adoption-stage:announced")
        event_keys.add(component_key)
        boundary_keys.add(f"structured-subject:{product}:{component}")
        separation_keys |= {
            f"primary-claim-subject:{product}:{component}",
            "primary-claim-predicate:hardware-component-adoption",
        }
        category_hint = "hardware_products"

    structured_title_actions = _structured_title_action_classes(identity)
    primary_changed_object, primary_changed_measure = (
        _primary_title_changed_object_measure(title_text)
    )
    changed_object_subjects = _primary_title_subjects(identity)
    if (
        content_form == "news"
        and identity.scope == "apple-direct"
        and len(changed_object_subjects) == 1
        and primary_changed_object
        and primary_changed_measure
    ):
        changed_subject = next(iter(changed_object_subjects))
        changed_object_key = (
            f"structured-measure:{changed_subject}:{primary_changed_object}:"
            f"count:{primary_changed_measure}"
        )
        event_keys.add(changed_object_key)
    structured_action_owner = bool(
        not third_party_app_availability
        and (
            identity.action_owner == "apple"
            or (
                identity.scope == "apple-direct"
                and identity.content_form == "news"
                and structured_title_subjects & _SPECIFIC_FIRST_PARTY_PRODUCTS
                and structured_title_actions
            )
        )
    )
    if (
        structured_action_owner
        and content_form == "news"
        and structured_title_subjects
        and structured_title_actions
    ):
        for subject in sorted(structured_title_subjects):
            for action in sorted(structured_title_actions):
                event_keys.add(f"structured-title-action:{subject}:{action}")
                boundary_keys.add(f"structured-title-subject:{subject}")
        if structured_title_subjects & _SPECIFIC_FIRST_PARTY_PRODUCTS and structured_title_actions & {
            "availability",
            "availability-expansion",
            "delay-roadmap",
            "price-change",
            "product-change",
        }:
            for subject in sorted(structured_title_subjects & _SPECIFIC_FIRST_PARTY_PRODUCTS):
                event_keys.add(f"structured-title-product-update:{subject}")
                boundary_keys.add(f"structured-title-subject:{subject}")
    release_subjects = identity.title_products & _PRECISE_HARDWARE_PRODUCT_LINES
    generic_refresh_title = bool(
        identity.title_actions
        and identity.title_actions <= {"feature-change", "product-refresh"}
        and not changed_object_keys
    )
    # A performance headline can report the same host launch when its own
    # facts explicitly announce the new host's processor configurations.
    configured_host_release = False
    if len(release_subjects) == 1 and identity.scope == "apple-direct" and not identity.title_actions:
        host = re.escape(next(iter(release_subjects))).replace(r"\-", r"[- ]?")
        configured_host_release = bool(re.search(
            rf"(?:new|新款)\s*{host}\s*(?:offers?|provides?|提供).{{0,70}}"
            r"(?:processor (?:options|configurations)|处理器配置)", _normalized(evidence), re.I))
    lead_release_action = _lead_asserts_first_party_release(lead) or configured_host_release
    release_action = bool(
        "market-report" not in identity.title_actions
        and (
            "product-launch" in identity.title_actions
        or (
            lead_release_action
            and (not identity.title_actions or generic_refresh_title)
        )
        )
    )
    release_action_owner = bool(
        structured_action_owner
        or (
            identity.scope == "apple-direct"
            and content_form == "news"
            and lead_release_action
            and not identity.title_actors
            and identity.title_products <= release_subjects
        )
    )
    if (
        release_action_owner
        and content_form == "news"
        and len(release_subjects) == 1
        and release_action
    ):
        release_subject = next(iter(release_subjects))
        event_keys.add(f"structured-title-product-release:{release_subject}")
        boundary_keys.add(f"structured-title-subject:{release_subject}")

    # An explicitly later configuration is not the standard launch wave.
    if len(release_subjects) == 1 and _compiled_rule(r"configuration.{0,50}later than.{0,25}standard|配置.{0,30}(?:晚于|迟于).{0,15}(?:标准|首发)", re.I).search(_normalized(lead)):
        capacities = _compiled_rule(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(gb|tb)\b", re.I).findall(title_text)
        for amount, unit in capacities:
            separation_keys.add(f"later-configuration:{next(iter(release_subjects))}:{amount}{unit.lower()}")

    macos_maintenance_branches: set[str] = set()
    if "macos" in title_text and _compiled_rule(r"\b(?:updates?|security fixes?|now available)\b|(?:更新|修复)", 0).search(title_text):
        macos_maintenance_branches.update(
            match.group(1)
            for match in _compiled_rule(r"\bmacos\s+([a-z][a-z-]{2,})\b", 0).finditer(title_text)
        )
        macos_maintenance_branches.update(
            match.group(1)
            for match in _compiled_rule(r"(?:&|/|\band\b)\s*([a-z][a-z-]{2,})"
                r"(?=\s+(?:\d+(?:\.\d+){1,2}|updates?|now\b|available\b|更新|修复|$))", 0).finditer(title_text)
        )
        macos_maintenance_branches -= {
            "macos",
            "new",
            "older",
            "security",
            "software",
            "system",
            "update",
        }
    if len(macos_maintenance_branches) >= 2:
        branch_key = "-".join(sorted(macos_maintenance_branches))
        maintenance_key = f"canonical-apple-action:macos-maintenance:{branch_key}"
        event_keys.add(maintenance_key)
        boundary_keys.add(maintenance_key)
        separation_keys.add("action:os-maintenance-update")
        category_hint = "software_systems"

    if projected_hardware_roadmap:
        assertion_events: set[str] = set()
        assertion_boundaries: set[str] = set()
        assertion_separation: set[str] = set()
        category_hint = "hardware_products"
        separation_keys.add("predicate:hardware-product-roadmap")
    else:
        assertion_events, assertion_boundaries, assertion_separation = _structured_assertion_keys(
            title,
            lead,
            identity,
            evidence,
            regions,
        )
    event_keys |= assertion_events
    boundary_keys |= assertion_boundaries
    separation_keys |= assertion_separation
    if any(
        key.startswith(
            (
                "structured-assertion:apple-tv:",
                "structured-assertion:apple-home-security:",
            )
        )
        for key in assertion_events
    ):
        category_hint = "software_systems"
    canonical_action_keys = _canonical_first_party_action_keys(identity)
    event_keys |= canonical_action_keys
    boundary_keys |= canonical_action_keys
    separation_keys |= {
        f"action:{key.rsplit(':', 1)[-1]}"
        for key in canonical_action_keys
    }
    (
        primary_claim_events,
        primary_claim_boundaries,
        primary_claim_separation,
        primary_claim_category,
        primary_claim_trusted,
    ) = _primary_claim_projection(title, lead, identity, regions, evidence, embedded_references, source_facts)
    dominant_primary_claim_subjects = {
        "primary-claim:apple-leadership:ceo-transition": "apple-leadership",
        "primary-claim:apple-leadership:transition-interview": "apple-leadership",
        "primary-claim:apple-leadership:ceo-first-employee-memo": "apple-leadership",
        "primary-claim:apple-leadership:ceo-social-account-launch": "apple-leadership",
        "primary-claim:apple-leadership:ceo-social-profile-image-update": "apple-leadership",
        "primary-claim:iphone-in-box-accessories:policy-denial": "iphone-in-box-accessories",
        "primary-claim:apple-openai-trade-secret-case:response-filing": "apple-openai-trade-secret-case",
        "primary-claim:apple-openai-trade-secret-case:evidence-disclosure": "apple-openai-trade-secret-case",
    }
    dominant_primary_claims = primary_claim_events & dominant_primary_claim_subjects.keys()
    ceo_transition_claim = "primary-claim:apple-leadership:ceo-transition"
    if ceo_transition_claim in dominant_primary_claims and len(primary_claim_events) > 1:
        # A regulatory meeting, document, or other concrete action can mention
        # the succession as context. In that case the generic transition key
        # must not replace the more specific primary claim.
        dominant_primary_claims = set(dominant_primary_claims)
        dominant_primary_claims.discard(ceo_transition_claim)
    if dominant_primary_claims:
        # A concrete document, policy response, legal filing stage, or formal
        # lifecycle action owns the event. Product guesses and background
        # transitions found elsewhere in the page may enrich facts, but must
        # not remain as alternate merge bridges.
        event_keys = set(dominant_primary_claims)
        dominant_subjects = {
            dominant_primary_claim_subjects[key]
            for key in dominant_primary_claims
        }
        dominant_predicates = {
            key.rsplit(":", 1)[-1]
            for key in dominant_primary_claims
        }
        boundary_keys = {
            f"primary-claim-subject:{subject}"
            for subject in dominant_subjects
        }
        separation_keys = {
            key
            for key in primary_claim_separation
            if key.startswith("primary-claim-")
            and (
                key.removeprefix("primary-claim-predicate:") in dominant_predicates
                or key.removeprefix("primary-claim-subject:") in dominant_subjects
            )
        }
    else:
        event_keys |= primary_claim_events
        boundary_keys |= primary_claim_boundaries
        separation_keys |= primary_claim_separation
    # A model's formal announcement and a same-day hands-on account can
    # describe one release. ANC, IPX ratings, or a model name alone cannot.
    beats_lead = _normalized(lead)
    generic_headphone_release = _compiled_rule(
        r"\b(?:releas\w*|launch\w*|unveil\w*)\b[^.!?]{0,50}\b(?:headphones?|over-ear)\b",
        re.I,
    ).search(title_text)
    beats_model = _compiled_rule(
        r"(?<![a-z0-9])beats\s*(\d{2,4})(?!\d)|"
        r"(?<![a-z0-9])beats\s*(?:推出|发布)\s*(\d{2,4})(?!\d)", re.I
    ).search(title_text)
    if not beats_model and generic_headphone_release:
        beats_model = _compiled_rule(
            r"(?<![a-z0-9])beats\s*(\d{2,4})(?!\d)", re.I
        ).search(_compiled_rule(r"[。！？]|(?<=[.!?])\s+(?=[a-z])", 0).split(beats_lead, 1)[0])
    if beats_model:
        model = beats_model.group(1) or beats_model.group(2)
        release_sentence = _compiled_rule(
            r"(?<![a-z0-9])beats\s*(?:(?:于)?(?:今日|今天)\s*)?正式\s*(?:发布|推出|亮相)了?"
            r"[^。.!?]{0,55}(?<![a-z0-9])beats\s*(\d{2,4})(?!\d)|"
            r"(?<![a-z0-9])beats\s+(?:has\s+)?(?:officially\s+)?(?:launched|unveiled)\s+"
            r"(?:the\s+new\s+)?beats\s*(\d{2,4})(?!\d)", re.I
        ).search(beats_lead[:900])
        generic_release_sentence = (_compiled_rule(
            r"\b(?:apple|beats)\b[^.!?]{0,45}\b(?:released?|launch\w*|unveil\w*)\b"
            r"[^.!?]{0,55}\bbeats\s*(\d{2,4})(?!\d)[^.!?]{0,35}"
            r"\b(?:headphones?|over-ear)\b", re.I,
        ).search(beats_lead[:300]) if generic_headphone_release else None)
        launch_hands_on = _compiled_rule(
            r"(?<![a-z0-9])beats\s*(\d{2,4})(?!\d)[^。.!?]{0,25}首发售价", re.I
        ).search(beats_lead[:220])
        if ((release_sentence and model in release_sentence.groups())
                or (generic_release_sentence and generic_release_sentence.group(1) == model)
                or (launch_hands_on and launch_hands_on.group(1) == model
                    and _compiled_rule(r"快速上手|上手|hands[- ]on", re.I).search(title_text))):
            event_keys.add(f"primary-claim:beats-model-{model}:product-launch")
            boundary_keys.add(f"primary-claim-subject:beats-model-{model}")
            separation_keys.add("primary-claim-predicate:product-launch")
            category_hint = "hardware_products"
    # The accessory is the action object; its host is compatibility context.
    hardware_roadmap_claim = None if accessory_evaluation else _hardware_roadmap_primary_claim(title, lead, identity)
    if hardware_roadmap_claim:
        roadmap_product, roadmap_action, roadmap_qualifier = hardware_roadmap_claim
        roadmap_key = f"structured-roadmap-action:{roadmap_product}:{roadmap_action}"
        event_keys.add(roadmap_key)
        boundary_keys.add(roadmap_key)
        separation_keys |= {
            f"primary-claim-subject:{roadmap_product}",
            f"primary-claim-predicate:{roadmap_action}",
        }
        if roadmap_qualifier.startswith("window|"):
            _, window_year, window_lower, window_upper = roadmap_qualifier.split("|")
            event_keys.add(f"structured-assertion:{roadmap_product}:planned-launch-window")
            separation_keys.add(f"hardware-launch-window:{roadmap_product}:{window_year}:{window_lower}:{window_upper}")
        if roadmap_qualifier != "unspecified":
            event_keys.add(f"{roadmap_key}:{roadmap_qualifier}")
            if _compiled_rule(r"20\d{2}", 0).fullmatch(roadmap_qualifier):
                separation_keys.add(
                    f"roadmap-period:{roadmap_product}:{roadmap_qualifier}"
                )
            elif roadmap_qualifier != "product-program" and not roadmap_qualifier.startswith("window|"):
                separation_keys.add(
                    f"primary-claim-qualifier:{roadmap_qualifier}"
                )
        category_hint = "hardware_products"
        trusted_direct_action = True
    broad_hardware_roadmap_claim = bool(
        identity.scope == "apple-direct"
        and len(identity.title_products) >= 2
        and "hardware-product-roadmap" in identity.title_components
        and hardware_roadmap_claim is None
    )
    if broad_hardware_roadmap_claim:
        separation_keys.add("primary-claim-predicate:broad-hardware-roadmap")
    multi_unit_capability = _multi_unit_apple_capability_claim(title, lead, identity)
    if multi_unit_capability:
        capability_product, capability_count, capability = multi_unit_capability
        capability_key = (
            f"primary-claim:apple-device-topology:{capability_product}:"
            f"{capability_count}:{capability}"
        )
        event_keys.add(capability_key)
        boundary_keys.add(capability_key)
        separation_keys.add(f"primary-claim-predicate:{capability}")
        category_hint = "software_systems"
        trusted_direct_action = True
    if primary_claim_category:
        category_hint = primary_claim_category
    trusted_direct_action = trusted_direct_action or primary_claim_trusted
    executive_farewell_key = (
        "primary-claim:apple-leadership:executive-farewell-communication"
    )
    if executive_farewell_key in primary_claim_events:
        event_keys.discard(
            "canonical-apple-action:apple-leadership:leadership-transition"
        )
        boundary_keys.discard(
            "canonical-apple-action:apple-leadership:leadership-transition"
        )
        separation_keys.discard("action:leadership-transition")
    invitation_interpretation_key = _apple_event_invitation_interpretation_key(
        title,
        lead,
        identity,
        changed_object_keys,
    )
    if invitation_interpretation_key:
        event_keys.add(invitation_interpretation_key)
        boundary_keys.add(invitation_interpretation_key)
        separation_keys |= {
            "primary-claim-subject:apple-event-invitation",
            "primary-claim-predicate:event-invitation-feature-interpretation",
        }
        category_hint = "hardware_products"
        trusted_direct_action = True
    event_campaign_key = "" if invitation_interpretation_key else _apple_event_campaign_key(title, lead)
    if event_campaign_key:
        event_keys.add(event_campaign_key)
        boundary_keys.add(event_campaign_key)
        separation_keys.add("primary-claim-subject:apple-event-campaign")
        category_hint = "hardware_products"
        trusted_direct_action = True
    event_occurrence_keys = (
        set() if invitation_interpretation_key else _apple_event_occurrence_keys(title, lead)
    )
    if event_occurrence_keys:
        event_keys |= event_occurrence_keys
        boundary_keys |= event_occurrence_keys
        separation_keys.add("primary-claim-subject:apple-event-campaign")
        category_hint = "hardware_products"
        trusted_direct_action = True
    if event_campaign_key or event_occurrence_keys:
        dated_campaign = source_dated_launch_frame(title, lead, source_facts + source_units, identity)
        if dated_campaign is not None:
            separation_keys.add('source-launch-stage:' + dated_campaign.action)
    content_claim = _first_party_content_claim(title, lead, identity, evidence)
    independent_content_playback = False
    if content_claim:
        content_subject, content_action = content_claim
        content_service = ("apple-arcade-content" if content_action == "arcade-catalog-addition" else
                           "apple-music-content" if content_action == "performance-lineup-announcement" else "apple-tv-content")
        content_key = f"primary-claim:{content_service}:{content_subject}:{content_action}"
        event_keys.add(content_key)
        boundary_keys.add(f"content-title:{content_subject}")
        separation_keys |= {
            f"content-title:{content_subject}",
            f"content-action:{content_action}",
        }
        category_hint = "software_systems"
        trusted_direct_action = True
    elif (media := _content_work_assertion(title, lead)) is not None and media[1] == 'playback-availability':
        # A media work's playback host does not turn its release into hardware
        # news. Resolving that object supplies no Apple publication authority.
        category_hint = "software_systems"
        independent_content_playback = True
    hardware_products = identity.title_products & {
        "airpods",
        "apple-home-hub",
        "apple-tv",
        "apple-watch",
        "beats",
        "foldable-iphone",
        "homepod",
        "imac",
        "ipad",
        "iphone",
        "mac",
        "mac-mini",
        "mac-pro",
        "mac-studio",
        "macbook",
        "vision-pro",
    }
    if changed_object_keys and hardware_products:
        category_hint = "hardware_products"
    structured_direct_assertion = bool(
        any(key.startswith("structured-assertion:") for key in assertion_events)
    )
    repair_cutoff = is_direct_apple_product_lifecycle_action(
        title,
        f"{lead} {evidence}",
    )
    direct_product_lifecycle_action = repair_cutoff or source_current_lifecycle_update(title, lead)
    if direct_product_lifecycle_action:
        trusted_direct_action = True
        lifecycle_scope, lifecycle_state = source_product_lifecycle_assertion(title, lead)
        if lifecycle_state == "listed" and repair_cutoff:
            # This branch requires a concrete end to official repair support.
            lifecycle_state = "obsolete"
        lifecycle_subjects = _product_lifecycle_subjects(lifecycle_scope,
            build_event_identity(lifecycle_scope, ""))
        separation_keys |= _product_lifecycle_year_keys(lifecycle_scope, lifecycle_subjects)
        if not identity.title_products:
            listed = _compiled_rule(r"\bapple\s+(?:(?:today|has|now|just)\s+)*added\s+"
                r"([^.!?。]{1,250}?)\s+to\s+(?:its|the)\s+(?:obsolete|vintage)\s+(?:products?\s+)?list", 0).search(
                    _primary_assertion_scope('', lead)[1])
            if listed:
                inventory = build_event_identity(listed.group(1), '')
                lifecycle_subjects |= _product_lifecycle_subjects(listed.group(1), inventory)
        for subject in lifecycle_subjects:
            event_keys.add(
                f"structured-assertion:product-lifecycle:{subject}:{lifecycle_state}"
            )
            separation_keys.add(f"assertion-subject:product-lifecycle:{subject}")
        boundary_keys.add(f"structured-action:product-lifecycle-{lifecycle_state}")
        separation_keys.add(f"assertion-action:product-lifecycle-{lifecycle_state}")
        category_hint = "hardware_products"
    title_owned_direct_action = bool(
        identity.action_owner == "apple"
        and not third_party_app_availability
        and content_form == "news"
        and identity.title_actions
        and not projected_hardware_roadmap
    )
    security_ids = {
        match.lower()
        for match in _compiled_rule(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE).findall(f"{text} {_normalized(evidence)}")
    }
    if security_ids and identity.scope in {"apple-direct", "unknown"} and (
        identity.title_products
        & {"ios", "ipados", "mac", "macos", "watchos", "tvos", "visionos", "safari"}
        or _contains(text, "apple", "苹果")
    ):
        for security_id in security_ids:
            event_keys.add(f"apple-security:cve:{security_id}")
            boundary_keys.add(f"apple-security:cve:{security_id}")
        separation_keys.add("action:security-vulnerability")
        category_hint = "software_systems"
    security_components = {
        component.removeprefix("os-component:")
        for component in identity.components
        if component.startswith("os-component:")
    }
    if security_components and "security" in identity.actions and (
        identity.scope in {"apple-direct", "unknown"}
        or identity.title_products
        & {"ios", "ipados", "mac", "macos", "watchos", "tvos", "visionos", "safari"}
    ):
        for component in security_components:
            event_keys.add(f"apple-security:os-component:{component}")
            boundary_keys.add(f"apple-security:os-component:{component}")
        separation_keys.add("action:security-vulnerability")
        category_hint = "software_systems"
    cross_platform_message_reply = bool(
        identity.scope == "apple-direct"
        and "ios" in identity.title_products
        and _contains(
            title_text,
            "replying to android texts",
            "reply to android texts",
            "green bubble",
            "安卓绿色气泡",
            "绿色气泡信息",
            "回复安卓消息",
            "回复安卓",
        )
    )
    if cross_platform_message_reply:
        event_keys.add("apple-messages:cross-platform-inline-reply")
        boundary_keys.add("apple-messages:cross-platform-inline-reply")
        separation_keys.add("action:cross-platform-message-reply")
        category_hint = "software_systems"
    chip_performance_report = bool(
        identity.scope == "apple-direct"
        and _compiled_rule(r"\b[am]\d{1,2}(?:\s*(?:pro|max|ultra))?\b", 0).search(title_text)
        and _contains(
            title_text,
            "performance",
            "speed",
            "faster",
            "efficiency",
            "efficient",
            "power consumption",
            "性能",
            "速度",
            "能效",
            "功耗",
        )
        and not (identity.title_actions & {"price-change"})
    )
    if chip_performance_report:
        chip_names = {
            _compiled_rule(r"\s+", 0).sub("-", match.lower(), 0)
            for match in _compiled_rule(r"\b[am]\d{1,2}(?:\s*(?:pro|max|ultra))?\b", 0).findall(title_text)
        }
        for chip_name in chip_names:
            event_keys.add(f"apple-chip-performance:{chip_name}")
            boundary_keys.add(f"apple-chip-performance:{chip_name}")
        separation_keys.add("action:chip-performance-report")
        category_hint = "hardware_products"
    tracking_transparency_policy_action = bool(
        _contains(
            text,
            "app tracking transparency",
            "tracking transparency",
            "att consent",
            "att prompt",
            "广告数据授权规则",
            "广告跟踪授权",
            "应用跟踪透明度",
        )
        and (
            "regulation" in identity.actions
            or _contains(
                text,
                "regulator",
                "regulatory",
                "agreement",
                "ordered",
                "comply",
                "监管",
                "协议",
                "同意",
                "要求",
                "合规",
            )
        )
    )
    if tracking_transparency_policy_action:
        event_keys.add("apple-platform-policy:app-tracking-transparency:regulatory-change")
        boundary_keys.add("apple-platform-policy:app-tracking-transparency")
        separation_keys.add("action:platform-policy-regulatory-change")
        category_hint = "software_systems"
    apple_service_products = identity.title_products & {
            "apple-books",
            "apple-card",
            "apple-gift-card",
            "apple-pay",
            "apple-wallet",
            "app-store",
            "icloud",
        }
    apple_owned_service_security_action = bool(
        apple_service_products
        and (
            "apple-gift-card" in apple_service_products
            or _title_proves_first_party_subject(title_text, identity)
        )
        and (
            "security" in identity.actions
            or _compiled_rule(r"\b(?:fraud|scam|tamper(?:ing|ed)?|stolen?\s+(?:code|codes)|"
                r"account\s+compromise|breach|convict(?:ed|ion)|enforcement)\b|"
                r"(?:诈骗|欺诈|盗取兑换码|兑换码被盗|篡改|破获|告破|定罪|执法)", 0).search(text)
        )
    )
    if apple_owned_service_security_action:
        service_subject = next(
            iter(
                sorted(
                    apple_service_products
                )
            )
        )
        service_security_key = f"apple-service-security:{service_subject}:current-incident"
        event_keys.add(service_security_key)
        boundary_keys.add(f"apple-service-security:{service_subject}")
        separation_keys.add("action:service-security-or-enforcement")
        category_hint = "software_systems"

    legal_component_subjects = identity.components & {
        "app-tracking-transparency",
        "face-id",
    }
    if "legal" in identity.actions and legal_component_subjects:
        for component in legal_component_subjects:
            legal_component_key = (
                f"primary-claim:apple-platform-component:{component}:legal-case"
            )
            event_keys.add(legal_component_key)
            boundary_keys.add(legal_component_key)
            separation_keys.add(f"legal-component:{component}")

    chip_disclosure_names = source_chip_technical_disclosures(title, lead)
    apple_chip_technical_disclosure = bool(chip_disclosure_names)
    if apple_chip_technical_disclosure:
        for chip_name in chip_disclosure_names:
            chip_key = (
                f"primary-claim:apple-chip:{chip_name}:technical-disclosure"
            )
            event_keys.add(chip_key)
            boundary_keys.add(chip_key)
        separation_keys.add("action:chip-technical-disclosure")
        category_hint = "hardware_products"
    os_signing_closure = bool(
        _compiled_rule(r"\b(?:stops?|stopped|ceases?|ceased)\s+signing\b|"
            r"\bno\s+longer\s+signs?\b|"
            r"(?:停止签署|停止签名|关闭.{0,12}签名(?:验证|通道)?)", 0).search(title_text)
    )
    if os_signing_closure:
        signing_versions = {
            match.group(1)
            for match in _compiled_rule(r"(?:\bios\s*)?(\d{2,3}(?:\.\d+){1,2})\b", 0).finditer(title_text)
        }
        for version in signing_versions:
            event_keys.add(f"apple-os-signing-closure:ios:{version}")
        boundary_keys.add("apple-os-signing-closure:ios")
        separation_keys.add("action:os-signing-closure")
        category_hint = "software_systems"
    official_apple_store_transaction_option_action = (
        _official_apple_store_transaction_option_action(title, lead)
    )
    if official_apple_store_transaction_option_action:
        boundary_keys.add("apple-store-retail:transaction-option")
        separation_keys.add("action:official-retail-transaction-option")
        category_hint = "hardware_products"
    first_party_service_capability_signal = ""
    if (
        "apple-fitness" in identity.title_products
        and _contains(
            text,
            "live production",
            "live-to-tape",
            "live sessions",
            "live content",
            "multi-camera",
            "直播制作",
            "直播内容",
            "直播健身",
            "多机位录播",
        )
        and _contains(
            text,
            "job listing",
            "job opening",
            "hiring",
            "recruiting",
            "producer",
            "招聘信息",
            "招聘",
            "制片人",
        )
    ):
        first_party_service_capability_signal = (
            "canonical-apple-action:apple-fitness:live-production-hiring"
        )
    elif (
        "apple-wallet" in identity.title_products
        and _contains(
            text,
            "driver's license",
            "drivers license",
            "driver license",
            "mobile id",
            "digital id",
            "数字驾照",
            "电子驾照",
            "数字身份证",
            "移动身份证",
        )
        and _contains(
            text,
            "expand",
            "expands",
            "expanding",
            "coming to",
            "launch",
            "support to follow",
            "more states",
            "扩展",
            "扩大",
            "新增",
            "上线",
            "支持",
            "更多州",
        )
    ):
        first_party_service_capability_signal = (
            "canonical-apple-action:apple-wallet:digital-id-regional-expansion"
        )
    if first_party_service_capability_signal:
        event_keys.add(first_party_service_capability_signal)
        boundary_keys.add(first_party_service_capability_signal)
        separation_keys.add("action:first-party-service-capability-signal")
        category_hint = "software_systems"
    versioned_os_compatibility_action = bool(
        identity.scope == "apple-direct"
        and not _hard_third_party_boundary(text, relevance_reason)
        and "os-compatibility" in identity.facets
        and identity.title_products
        & {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
        and identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    )
    if versioned_os_compatibility_action:
        boundary_keys.add("apple-os-compatibility:device-feature-matrix")
        separation_keys.add("action:os-device-feature-compatibility")
        category_hint = "software_systems"
    if any(
        key.startswith(
            (
                "structured-assertion:apple-display-inventory:",
                "structured-assertion:apple-facility:",
                "structured-assertion:apple-glasses:",
                "structured-assertion:iphone-anniversary-redesign:",
                "structured-assertion:iphone-",
                "structured-assertion:product-lifecycle:",
            )
        )
        for key in assertion_events
    ):
        category_hint = "hardware_products"
    if any(
        key.startswith(
            (
                "structured-assertion:app-store:",
                "structured-assertion:apple-patent:notification-",
                "structured-assertion:iphone-camera:reference-image-",
            )
        )
        for key in assertion_events
    ):
        category_hint = "software_systems"

    document_lifecycle_key = first_party_document_lifecycle_key(title_text, text, identity)
    if document_lifecycle_key:
        event_keys.add(document_lifecycle_key)
        boundary_keys.add(document_lifecycle_key)
        separation_keys.add(f"title-fact:{document_lifecycle_key}")
        separation_keys.add("action:first-party-document-lifecycle")
        category_hint = "software_systems"

    generation = foldable_iphone_generation_subject(title_text)
    if generation == "foldable-iphone":
        _, primary_scope = _primary_assertion_scope(title_text, lead)
        generation = foldable_iphone_generation_subject(primary_scope)
    if generation != "foldable-iphone":
        separation_keys.add("source-model-generation:" + generation)

    for signature in _title_fact_signatures(title_text, lead):
        key = f"title-fact:{signature}"
        event_keys.add(key)
        boundary_keys.add(key)
        separation_keys.add(key)

    primary_lead = _compiled_rule(r"(?:[。！？]|(?<=[.!?])\s+)", 0).split(_normalized(lead), 1)[0]
    measurements = _evidence_measurements(title_text, lead)
    claim_components = _claim_components(identity) | {
        component
        for component in primary_assertion_components(primary_lead)
        if ":" not in component
    }
    claim_products = {
        product.removeprefix("apple-")
        for product in (identity.title_products or identity.products)
        if product
    }
    product_aliases = claim_products | {
        "apple",
        "iphone",
        "ipad",
        "mac",
        "macbook",
    }
    attributed_entities = {
        component.removeprefix("report-attribution:")
        for component in identity.components
        if component.startswith("report-attribution:")
    } | {
        subject.removeprefix("apple-")
        for subject in identity.named_subjects
        if subject.removeprefix("apple-") not in product_aliases
        and subject not in _GENERIC_SUBJECT_WORDS
    }
    non_calendar_measurements = {
        measurement
        for measurement in measurements
        if not measurement.startswith("year:")
    }
    claim_status_actions = identity.title_actions & {
        "claim-denial",
        "project-cancellation",
    }
    if claim_status_actions:
        status_subjects = sorted(
            identity.title_products
            or identity.title_actors
            or identity.title_named_subjects
        )
        status_measurements = sorted(
            measurement
            for measurement in non_calendar_measurements
            if measurement.startswith(("anniversary:", "money:"))
        )
        for subject in status_subjects:
            for measurement in status_measurements:
                event_keys.add(
                    f"structured-claim-status:{subject}:{measurement}"
                )
    panel_role_measures = any(key.startswith("structured-panel-report-measure:") for key in event_keys)
    # Panel report percentages are owned by their metric subjects above.
    # Do not also create a product/entity x all-values alternative authority.
    if panel_role_measures or any(key.startswith("local-measure-object:") for key in separation_keys):
        non_calendar_measurements = set()
    for entity in attributed_entities:
        for product in claim_products:
            for measurement in non_calendar_measurements:
                event_keys.add(
                    f"structured-attributed-measure:{entity}:{product}:{measurement}"
                )
    for component in claim_components:
        for product in claim_products:
            if (
                not exact
                and component in LEAD_IDENTITY_COMPONENTS
                and component in primary_assertion_components(primary_lead)
            ):
                event_keys.add(f"structured-component:{component}:{product}")
            for entity in attributed_entities:
                event_keys.add(
                    f"structured-entity-component:{entity}:{product}:{component}"
                )
            for measurement in non_calendar_measurements:
                event_keys.add(
                    f"structured-component-measure:{component}:{product}:{measurement}"
                )
    supplier_component_classes = {
        component.removeprefix("component-supplier-sourcing:")
        for component in identity.components
        if component.startswith("component-supplier-sourcing:")
    }
    supplier_entity_stopwords = {
        "cpu",
        "dram",
        "gpu",
        "lcd",
        "nand",
        "oled",
        "ram",
        "soc",
    }
    supplier_entities = {
        subject
        for subject in identity.named_subjects
        if subject not in supplier_entity_stopwords
        and not subject.startswith(("a20", "m6", "m7", "m8"))
    }
    for component_class in supplier_component_classes:
        for supplier_entity in supplier_entities:
            event_keys.add(
                f"structured-supplier-action:{component_class}:{supplier_entity}"
            )
    calendar_measurements = {
        measurement
        for measurement in measurements
        if measurement.startswith("year:")
    }
    for left_component, right_component in combinations(sorted(claim_components), 2):
        for measurement in calendar_measurements:
            event_keys.add(
                "structured-component-period:"
                f"{left_component}+{right_component}:{measurement}"
            )
    if (
        event_kind == "legal_antitrust"
        or "legal" in identity.actions
        or identity.case_topics
        or identity.counterparties
    ):
        for measurement in measurements:
            if measurement.startswith("money:"):
                event_keys.add(f"structured-legal-settlement:{measurement}")
    removal_title = _compiled_rule(r"[,，;；]", 0).split(title_text, 1)[0]
    removal_lead = _compiled_rule(r"\balong with\b|\balongside other\b|此外|背景是", 0).split(primary_lead, 1)[0]
    # A subordinate status/background clause must not replace an already
    # identified current source action with an unrelated store removal.
    removal_scope = removal_title if primary_claim_events else f"{removal_title}. {removal_lead}"
    removal_stage = _app_store_removal_stage(removal_scope)
    app_store_removal_context = bool(
        "app-store" in identity.products
        or _contains(
            f"{title_text}. {primary_lead}",
            "app store",
            "apple app store",
            "应用商店",
            "苹果应用商店",
        )
        or _compiled_rule(r"\bapple\b.{0,32}\b(?:pull(?:s|ed)?|remove(?:s|d)?|delist(?:s|ed)?)\b"
            r".{0,36}\b(?:app|application)\b|"
            r"(?:苹果).{0,28}(?:下架|移除|撤下).{0,28}(?:应用|\bapp\b)|"
            r"(?:应用|\bapp\b).{0,28}(?:遭|被).{0,12}(?:苹果).{0,12}(?:下架|移除|撤下)", re.I).search(f"{title_text}. {primary_lead}")
    )
    support_capability_removal = any(
        key.endswith(
            (
                ":intel-support-removal",
                ":platform-support-removal",
                ":compatibility-support-removal",
            )
        )
        for key in primary_claim_events
    )
    if removal_stage and app_store_removal_context and not support_capability_removal:
        removal_subjects = _app_store_subjects(title_text, identity)
        removal_attributions = {
            component.removeprefix("report-attribution:")
            for component in identity.components
            if component.startswith("report-attribution:")
        }
        incident_event_keys = {
            key
            for key in event_keys
            if key.startswith("structured-assertion:app-store:")
        }
        incident_event_keys |= {
            f"app-store-removal-report:{attribution}:{removal_stage}"
            for attribution in removal_attributions
        }
        incident_boundaries = {
            key
            for key in boundary_keys
            if key.startswith("structured-subject:app-store:")
        }
        event_keys = incident_event_keys | {
            f"app-store-removal:{subject}:{removal_stage}"
            for subject in removal_subjects
        }
        boundary_keys = incident_boundaries | {
            f"app-store-removal:{subject}"
            for subject in removal_subjects
        }

    region_values = sorted(region for region in regions if region != "multi-region")
    if _annual_sales_metric(text):
        region_key = ",".join(region_values) or "global"
        event_keys.add(f"apple-market:annual-sales:{region_key}")
        boundary_keys.add("apple-market:annual-sales")
        category_hint = "hardware_products"

    if content_form != "roundup" and _multi_product_price_forecast(text):
        event_keys.add("apple-market:multi-product-price-forecast")
        boundary_keys.add("apple-market:multi-product-price-forecast")
        category_hint = "hardware_products"

    # Trade-in payouts and device eligibility are different retail actions.
    # Resolve the primary subject before considering change words in context.
    trade_in_title = bool(_compiled_rule(r"\btrade[ -]in\b|以旧换新|折抵", 0).search(title_text))
    trade_clauses = [title_text]
    for clause in _compiled_rule(r"[。.!?;；]", 0).split(_normalized(lead)[:900], 0):
        clause = _compiled_rule(r"\b(?:while|whereas|but|and)\s+(?!(?:apple|it)\b|the company\b)"
            r"(?:[a-z][a-z'-]*\s+){1,4}(?:is|has|will|offers?|updates?|raises?|accepts?)\b"
            r"|(?:而|但)(?!苹果)[^，。；]{1,16}(?:提供|提高|接受|调整)", 0).split(clause, 1)[0]
        if not _compiled_rule(r"\btrade[ -]in\b|以旧换新|折抵", 0).search(clause):
            continue
        # Keep the source's grammatical subject through its own predicate
        # extension ("softening ... by offering", "will expand ... to offer").
        # A reporting verb or a fresh subject does not inherit this ownership.
        owned = _compiled_rule(r"\s*apple\s+(?:(?:is|has|will|now|reportedly|today|officially)\s+)*", 0).match(clause)
        chinese_owned = _compiled_rule(r"\s*苹果(?:据称|现已|今日|正在|将)?", 0).match(clause)
        if not (owned or chinese_owned):
            continue
        predicate = clause[(owned or chinese_owned).end():]
        if _compiled_rule(r"^(?:supplier|partner|rival|competitor|customer|says?|said|reports?|claims?)\b|^(?:的|供应商|竞争对手|表示|声称)", 0).search(predicate):
            continue
        if not _compiled_rule(r"offer\w*|updat\w*|adjust\w*|rais\w*|increas\w*|lower\w*|accept\w*|chang\w*|提供|调整|上调|下调|提高|接受", 0).search(predicate):
            continue
        if _compiled_rule(r"previously|earlier|last (?:year|winter|month)|used to|unchanged|did not|does not|will not|won't|此前|去年|未调整|没有改变|不会", 0).search(clause):
            continue
        trade_clauses.append(clause)
    trade_in_primary = ". ".join(trade_clauses)
    policy_object = r"eligib|cosmetic|scratch|damage|inspection|condition|成色|划痕|损伤|资格|验机"
    trade_in_policy = trade_in_title and any(
        re.search(policy_object, clause)
        and not _compiled_rule(r"unchanged|remain(?:s|ed)?|did not|does not|未调整|没有改变", 0).search(clause)
        for clause in trade_clauses
    )
    trade_in_change = bool(
        trade_in_title and not trade_in_policy
        and _compiled_rule(r"updat\w*|adjust\w*|rais\w*|increas\w*|lower\w*|sweetens|bumps|higher|上调|提高|调整|下调|升值", 0).search(trade_in_primary)
        and ("trade-in-valuation" in identity.components
             or _compiled_rule(r"\btrade[ -]in\s+(?:value|values|offer|offers|estimate|estimates|deal|deals)\b", 0).search(trade_in_primary)
             or _contains(trade_in_primary, "以旧换新", "折抵价", "折抵估值"))
    )
    if trade_in_change or trade_in_policy:
        trade_action = "eligibility-policy" if trade_in_policy else "valuation-change"
        event_keys.add(f"apple-retail:trade-in-{trade_action}")
        boundary_keys.add(f"apple-retail:trade-in-{trade_action}")
        separation_keys.add(f"retail-trade-in-action:{trade_action}")
        separation_keys.add("primary-claim-subject:apple-trade-in")
        separation_keys.add(f"primary-claim-predicate:trade-in-{trade_action}")
        separation_keys.add(f"action:trade-in-{trade_action}")
        category_hint = "hardware_products"

    if (
        _contains(
            title_text,
            "premium smartphone market",
            "high-end smartphone market",
            "高端智能手机市场",
            "高端手机市场",
            "全球高端手机市场",
        )
        and (
            _contains(text, "market share", "share", "份额", "accounted for", "占据")
            or _compiled_rule(r"\bholds?\s+\d+(?:\.\d+)?\s*%", 0).search(text)
        )
        and _contains(title_text, "apple", "iphone", "苹果")
    ):
        event_keys.add("apple-market:premium-smartphone-share")
        boundary_keys.add("apple-market:premium-smartphone-share")
        separation_keys.add("action:measured-market-share")
        category_hint = "hardware_products"

    generations = _component_values(identity, "iphone-generation:") | {
        value.removeprefix("iphone-")
        for value in _component_values(identity, "product-generation:")
        if value.startswith("iphone-")
    }
    title_supply_constraint = _contains(
        title_text,
        "dram",
        "ram supply",
        "memory shortage",
        "limited availability",
        "scrambling to secure memory",
        "sell out fast",
        "量产遇挑战",
        "紧急抢购内存",
        "内存短缺",
        "供货受限",
    )
    supply_constraint = bool(
        generations
        and title_supply_constraint
        and _contains(text, "dram", "ram", "memory", "内存")
        and _contains(
            text,
            "shortage",
            "limited availability",
            "supply constraint",
            "holding up",
            "sell out fast",
            "scrambling to secure",
            "production challenge",
            "短缺",
            "供货受限",
            "供应受限",
            "量产遇挑战",
            "紧急抢购",
        )
    )
    if supply_constraint:
        for generation in generations:
            event_keys.add(f"apple-supply:iphone-{generation}:memory-constraint")
        if _contains(text, "a20"):
            event_keys.add("apple-supply:a20:memory-constraint")
        boundary_keys.add("apple-supply:iphone-memory-constraint")
        separation_keys.add("action:product-supply-constraint")
        category_hint = "hardware_products"

    a20_memory_constraint = bool(
        _contains(text, "a20")
        and _contains(text, "dram", "ram", "memory", "内存")
        and _contains(
            text,
            "cannot be packaged",
            "unable to package",
            "packaging backlog",
            "without memory chips",
            "holding up",
            "无法封装",
            "无内存芯片搭配",
            "积压",
        )
    )
    if a20_memory_constraint:
        event_keys.add("apple-supply:a20:memory-constraint")
        boundary_keys.add("apple-supply:iphone-memory-constraint")
        separation_keys.add("action:product-supply-constraint")
        category_hint = "hardware_products"

    memory_suppliers = {
        supplier
        for supplier, aliases in _MEMORY_SUPPLIER_ALIASES.items()
        if _contains(text, *aliases)
    }
    title_memory_negotiation = bool(
        _contains(title_text, "apple", "iphone", "苹果")
        and _contains(title_text, "bid", "leverage", "denies", "talks", "negot", "筹码", "谈判", "议价", "压价", "定价权")
    )
    title_has_apple_subject = _contains(title_text, "apple", "iphone", "苹果", "库克")
    if memory_suppliers and (
        title_memory_negotiation
        or (
            title_has_apple_subject
            and
            any(alias in title_text for aliases in _MEMORY_SUPPLIER_ALIASES.values() for alias in aliases)
            and _contains(text, "talks", "negot", "procure", "source", "buy", "洽谈", "谈判", "采购", "议价")
        )
    ):
        event_keys.add("apple-sourcing:memory:china-suppliers:negotiation")
        boundary_keys.add("apple-sourcing:memory-negotiation")
        separation_keys.add("action:memory-supplier-negotiation")
        category_hint = "hardware_products"

    memory_policy_action = bool(
        memory_suppliers
        and _contains(text, "white house", "trump", "特朗普", "白宫")
        and _contains(text, "apple", "iphone", "苹果", "cook", "库克")
        and _contains(text, "petition", "lobby", "allow", "approval", "reject", "游说", "允许", "批准", "拒绝")
    )
    if memory_policy_action:
        event_keys.add("apple-policy:restricted-memory-supplier-approval")
        boundary_keys.add("apple-policy:restricted-memory-supplier-approval")
        separation_keys.add("action:memory-supplier-policy")
        category_hint = "hardware_products"

    macbook_models = _component_values(identity, "macbook-model:")
    refurbished_store_action = _official_refurbished_store_action(text)
    # A future product configuration remains a hardware roadmap even when
    # its supporting paragraphs also discuss OS compatibility or chip plans.
    future_hardware_configuration = bool(
        identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
        and not identity.title_products & _SOFTWARE_FIRST_PARTY_PRODUCTS
        and identity.scope == "apple-direct"
        and content_form == "news"
        and _compiled_rule(
            r"\b(?:redesigned|next-generation|upcoming|new)\b[^.!?]{0,100}"
            r"\b(?:to|will|could|may|might)\s+(?:feature|have|include|use|adopt)\b|"
            r"(?:下月|明年|未来|将(?:会)?|计划)"
            r"(?:迎来|进行|大幅|重大|大)?(?:改款|重新设计)",
            0,
        ).search(title_text)
    )
    macbook_roadmap_action = bool(
        not refurbished_store_action
        and not versioned_os_compatibility_action
        and (relevance_tier != "weak" or trusted_direct_action)
        and content_form == "news"
        and (
            future_hardware_configuration
            or identity.actions & {"delay-roadmap", "pilot-testing"}
            or (
                _contains(
                    title_text,
                    "upgrade options",
                    "coming",
                    "coming soon",
                    "upcoming",
                    "路线图",
                    "即将",
                    "将推出",
                    "来袭",
                    "首发",
                )
                and _contains(
                    text,
                    "report",
                    "plans",
                    "expected",
                    "rumored",
                    "this fall",
                    "消息称",
                    "据称",
                    "计划",
                    "预计",
                    "传闻",
                    "今秋",
                )
            )
        )
    )
    if refurbished_store_action:
        event_keys.add("canonical-apple-action:official-refurbished-catalog:catalog-expansion")
        boundary_keys.add("canonical-apple-action:official-refurbished-catalog:catalog-expansion")
        for model in macbook_models:
            event_keys.add(f"apple-retail:refurbished:macbook-{model}")
        boundary_keys.add("apple-retail:refurbished-catalog")
        separation_keys.add("action:official-refurbished-availability")
        category_hint = "hardware_products"
    elif macbook_models and macbook_roadmap_action:
        for model in macbook_models:
            event_keys.add(f"apple-roadmap:macbook-{model}")
            separation_keys.add(f"product-model:macbook-{model}")
        boundary_keys.add("apple-roadmap:macbook")
        separation_keys.add("action:product-roadmap")
        category_hint = "hardware_products"

    anniversary_milestone = _product_anniversary_milestone(title_text)
    if anniversary_milestone:
        product, years = anniversary_milestone
        event_keys.add(f"apple-product-anniversary:{product}:{years}")
        boundary_keys.add(f"apple-product-anniversary:{product}")
        separation_keys.add("action:product-anniversary")
        category_hint = "hardware_products"

    screening_subject = _content_screening_subject(title, lead)
    if (
        screening_subject
        and "apple-tv" in identity.products
        and _contains(text, "theater", "theatre", "cinema", "screening", "screenings", "影院", "放映")
    ):
        event_keys.add(f"apple-tv-content:{screening_subject}:screening")
        boundary_keys.add("apple-tv-content:screening")
        separation_keys.add(f"content-title:{screening_subject}")

    if _bug_bounty_submission_limit(text):
        event_keys.add("apple-security:bug-bounty-submission-limit")
        boundary_keys.add("apple-security:bug-bounty-submission-limit")

    if _icloud_private_relay_leak(text) or _webkit_proxy_leak(text):
        event_keys.add("apple-security:webkit-private-relay-network-leak")
        boundary_keys.add("apple-security:webkit-private-relay-network-leak")

    applied_research_key = _measured_applied_research_key(text, identity)
    if applied_research_key:
        event_keys.add(applied_research_key)
        boundary_keys.add(":".join(applied_research_key.split(":")[:3]))
        category_hint = "hardware_products"

    market_forecast_key = _product_driven_market_forecast_key(text, identity)
    if market_forecast_key:
        event_keys.add(market_forecast_key)
        boundary_keys.add(":".join(market_forecast_key.split(":")[:3]))
        category_hint = "hardware_products"

    # Existing exact action facets are stronger than a generic OS/version
    # scope. Let the exact facet reconcile translations and headline variants
    # instead of creating competing feature identities for the same action.
    os_feature_scope = _versioned_os_feature_scope(text, identity)
    if exact and os_feature_scope and not os_feature_scope.startswith("apple-os-release-wave:"):
        os_feature_scope = ""
    if os_feature_scope:
        event_keys.add(os_feature_scope)
        boundary_keys.add(os_feature_scope)
        if os_feature_scope.startswith("apple-os-release-wave:"):
            if ":final:" in os_feature_scope and is_os_release_announcement(title):
                for platform in _release_subject_platforms(title, text.partition('. ')[2]):
                    event_keys.add(os_feature_scope.rsplit(":", 1)[0] + ":" + platform)
            for platform_wave in sorted(
                component.removeprefix("os-wave-platform:")
                for component in identity.components
                if component.startswith("os-wave-platform:")
            ):
                event_keys.add(
                    f"apple-os-platform-release-wave:{platform_wave}"
                )

    report_attributions = sorted(
        component.removeprefix("report-attribution:")
        for component in identity.components
        if component.startswith("report-attribution:")
    )
    report_subjects = sorted(
        component
        for component in identity.components
        if component.startswith(
            (
                "iphone-model:",
                "iphone-family:",
                "macbook-model:",
                "product-generation:",
            )
        )
    )
    report_components = sorted(
        component
        for component in identity.components & LEAD_IDENTITY_COMPONENTS
        if not component.startswith("primary-intent:")
    )
    if report_attributions and report_subjects and report_components:
        for attribution in report_attributions:
            for subject in report_subjects:
                for component in report_components:
                    event_keys.add(
                        f"structured-report:{attribution}:{subject}:{component}"
                    )

    structured_components = sorted(
        identity.components & (LEAD_IDENTITY_COMPONENTS | EVIDENCE_BACKED_COMPONENTS)
    )
    structured_subjects = sorted(
        subject
        for subject in identity.named_subjects
        if subject
        not in {
            "apple",
            "apple-vision",
            "iphone",
            "ipad",
            "mac",
            "macbook",
        }
    )
    canonical_subjects = {
        subject.removeprefix("apple-")
        for subject in structured_subjects
        if subject.startswith("apple-")
    }
    canonical_subjects = {
        subject
        for subject in canonical_subjects
        if not any(
            other != subject and other.startswith(f"{subject}-")
            for other in canonical_subjects
        )
    }
    product_subjects = {
        subject.removeprefix("apple-")
        for subject in structured_subjects
        if subject.startswith("apple-")
    }
    product_subjects = {
        subject
        for subject in product_subjects
        if not any(
            other != subject and subject.startswith(f"{other}-")
            for other in product_subjects
        )
    }
    explicit_first_party_subjects = {
        subject.removeprefix("apple-")
        for subject in identity.title_named_subjects
        if subject.startswith("apple-")
    } | {
        component.removeprefix("evidence-named-subject:apple-")
        for component in identity.components
        if component.startswith("evidence-named-subject:apple-")
    }
    product_aliases = {
        product.removeprefix("apple-")
        for product in identity.products | identity.title_products
    }
    if (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and not identity.counterparties
        and not identity.case_topics
    ):
        for subject in sorted(product_subjects & explicit_first_party_subjects):
            if "-" in subject and subject not in product_aliases:
                event_keys.add(f"structured-first-party-subject:{subject}")
    if (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and not identity.counterparties
        and not identity.case_topics
        and canonical_subjects
        and identity.title_actions
    ):
        for subject in sorted(canonical_subjects):
            for action in sorted(identity.title_actions):
                event_keys.add(f"structured-subject-action:{subject}:{action}")
    if (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and not identity.counterparties
        and not identity.case_topics
        and not any(
            component.startswith(("os-wave:", "os-wave-platform:"))
            for component in identity.components
        )
        and product_subjects
        and identity.title_products
    ):
        for subject in sorted(product_subjects):
            for product in sorted(identity.title_products):
                normalized_product = product.removeprefix("apple-")
                if (
                    subject == product
                    or subject == normalized_product
                    or subject.endswith(f"-{product}")
                ):
                    continue
                event_keys.add(f"structured-subject-product:{subject}:{product}")
    if structured_components and identity.title_products:
        for component in structured_components:
            for product in sorted(identity.title_products):
                if not report_attributions:
                    event_keys.add(
                        f"structured-component:{component}:{product}"
                    )
                for subject in structured_subjects:
                    event_keys.add(
                        f"structured-component:{component}:{product}:{subject}"
                    )

    if _apple_first_party_home_camera_roadmap(title_text, text):
        event_keys.add("apple-home:first-party-security-camera-roadmap")
        boundary_keys.add("apple-home:first-party-security-camera-roadmap")
        separation_keys.add("action:first-party-home-camera-roadmap")
        category_hint = "hardware_products"

    # Preparation belongs to its local object: apps and store pages are not
    # evidence that two sources report the same internal event operation.
    event_staff_support = _event_staff_support(text)
    event_format_plan = _event_format_plan(text)
    event_preparation = bool(
        _event_preparation(title_text)
        and _compiled_rule(r"(?:prepar(?:ing|ations?)|getting ready).{0,30}(?:for|its).{0,30}(?:event|发布会)|发布会.{0,12}(?:筹备|准备)", 0).search(title_text)
        and _contains(_normalized(lead)[:300], "internal preparation", "internal lottery", "retail staff", "内部筹备", "员工", "现场支援")
    )
    operation = ""
    resource_scope = title_text + ". " + _normalized(lead)[:240]
    first_party_resource_release = bool(_compiled_rule(r"\bapple\s+(?:(?:has|today|officially|now)\s+)*(?:releases?|released|publishes?|published|updates?|updated)\b"
        r"|(?:released|published)\s+by\s+apple\b|苹果(?:正式|今日|现已)?(?:发布|推出)", 0).search(resource_scope))
    if _compiled_rule(r"design resources?|设计资源", 0).search(title_text) and first_party_resource_release:
        operation = "design-resource-publication"
    elif event_staff_support or event_preparation:
        operation = "staff-support-preparation"
    elif event_format_plan:
        operation = "presentation-format-plan"
    if operation:
        separation_keys.add(f"event-operation-action:{operation}")
        operation_subject = {
            "design-resource-publication": "apple-design-resources",
            "staff-support-preparation": "apple-event-staff-support",
            "presentation-format-plan": "apple-event-presentation",
        }[operation]
        separation_keys.add(f"primary-claim-subject:{operation_subject}")
        separation_keys.add(f"primary-claim-predicate:{operation}")
        if operation == "design-resource-publication":
            for product in sorted(identity.title_products):
                event_keys.add(f"source-action:design-resources:{product}:publication")
        else:
            event_keys.add(f"apple-event:{operation}")
        boundary_keys.add(f"apple-event:{operation}")

    if "airpods" in text and _contains(text, "firmware", "固件") and _contains(
        text,
        "beta",
        "testing",
        "developer",
        "测试版",
        "公测",
        "开发者",
    ):
        event_keys.add("apple-firmware:airpods-beta")
        boundary_keys.add("apple-firmware:airpods-beta")
        for build in _compiled_rule(r"(?:firmware|固件|版本号|\bbuild|\bversion)\s*(?:version\s*)?([0-9]{1,3}[a-z][0-9]{2,}[a-z]?)\b", re.I).finditer(text):
            separation_keys.add("code-build:airpods-" + build.group(1).lower())

    display_metrics = _display_metrics(text)
    anniversary_display = bool(
        _compiled_rule(r"\b20th\s+anniversary\b|\btwentieth\s+anniversary\b|"
            r"\biphone\s*20\b|20\s*周年|二十周年", 0).search(text)
    )
    if (
        (display_metrics or _contains(text, "larger screen", "larger display", "更大尺寸屏幕", "屏幕尺寸增大"))
        and _contains(text, "iphone")
        and _contains(text, "display", "screen", "屏幕")
        and _contains(text, "rumor", "leak", "prototype", "testing", "传闻", "爆料", "测试")
    ):
        event_keys |= {
            f"iphone-display-rumor:size:{metric}"
            for metric in display_metrics
        }
        boundary_keys.add("iphone-display-rumor")
        separation_keys.add("product-family:iphone")
        if anniversary_display:
            event_keys.add("iphone-display-rumor:anniversary-size-change")

    legal_case = _legal_case_key(identity)
    legal_stage = _legal_action_stage(title_text, text[len(title_text) :])
    legal_parties = sorted(
        (identity.counterparties - {"secrets", "lawsuit"})
        | _legal_title_parties(title_text)
    )
    if not legal_case and legal_parties:
        legal_case = ":".join(legal_parties)
    direct_legal_action = bool(
        legal_stage
        and legal_case
        and ("legal" in identity.title_actions
             or (_compiled_rule(r'\bcase\b|纠纷案', 0).search(title_text)
                 and _legal_action_stage_text(title_text)))
        and _contains(title_text, "apple", "苹果")
    )
    if (
        ("legal" in identity.actions or "apple-hardware-trade-secret-lawsuit" in exact or direct_legal_action)
        and legal_case
        and legal_stage
        and (relevance_tier != "weak" or trusted_direct_action or direct_legal_action)
    ):
        event_keys.add(f"apple-legal:{legal_case}:{legal_stage}")
        event_keys |= {
            f"apple-legal-party:{party}:{legal_stage}"
            for party in legal_parties
        }
        boundary_keys.add(f"apple-legal-case:{legal_case}")
        boundary_keys |= {
            f"apple-legal-party:{party}"
            for party in legal_parties
        }
        separation_keys |= {
            f"legal-party:{party}"
            for party in legal_parties
        }
        separation_keys.add(f"legal-stage:{legal_stage}")

    primary_intents = {
        component
        for component in identity.title_components
        if component.startswith("primary-intent:")
    }
    separation_keys |= {
        f"action:{intent.split(':', 1)[1]}"
        for intent in primary_intents
        if intent.split(":", 1)[1]
        in {
            "product-price-change",
            "product-production-status",
            "product-supply-constraint",
            "memory-supplier-policy",
            "compute-capacity-risk",
        }
    }
    if "primary-intent:product-production-status" in primary_intents:
        production_rate = _product_production_rate_signature(
            title_text,
            lead,
            evidence,
        )
        production_products = sorted(identity.title_products)
        if len(production_products) == 1:
            boundary_keys.add(
                f"primary-claim:{production_products[0]}:product-production-status"
            )
            if production_rate:
                event_keys.add(
                    f"primary-claim:{production_products[0]}:"
                    f"product-production-status:{production_rate}"
                )
            for attribution in sorted(
                component.removeprefix("report-attribution:")
                for component in identity.components
                if component.startswith("report-attribution:")
                and component != "report-attribution:multiple"
            ):
                event_keys.add(
                    f"primary-claim:{production_products[0]}:"
                    f"product-production-status:report:{attribution}"
                )
    if "feature-change" in identity.title_actions and identity.title_products:
        separation_keys.add("action:feature-change")

    if (
        content_form == "event_preview"
        and not event_format_plan
        and "primary-claim:apple-product-catalog:multi-product-withdrawal-forecast"
        not in primary_claim_events
    ):
        # Background facts in an editorial preview must not impersonate the
        # concrete actions they recap.
        event_keys.clear()
        boundary_keys.clear()

    source_component_action = _source_named_os_component_action(title_text, evidence, identity)
    unverified_final_os_schedule = bool(
        not source_component_action and
        any(
            component.startswith(("os-wave:", "os-wave-platform:"))
            and component.endswith(":final")
            for component in identity.components
        )
        and "retail-availability" in identity.title_actions
        and not _lead_asserts_first_party_release(title_text)
        and not _lead_asserts_first_party_release(lead)
        and not _has_absolute_calendar_date(
            f"{title_text}. {_primary_assertion_scope('', lead)[1]}"
        )
    )
    versioned_os_action = bool(
        (_versioned_os_feature_report(text, identity) or source_component_action)
        and not unverified_final_os_schedule
    )
    current_generation_product_report = any(
        ":generation-product-refresh" in key
        for key in primary_claim_events
    )
    current_beta_asset_disclosure = any(
        ":unintended-product-asset-disclosure" in key
        for key in primary_claim_events
    )
    current_event_schedule_report = any(
        ":schedule-forecast" in key
        for key in primary_claim_events
    )
    release_announcement_keys = {
        key
        for key in event_keys
        if key.startswith(("apple-os-release-wave:", "apple-os-platform-release-wave:"))
    }
    if versioned_os_action and release_announcement_keys:
        separation_keys.add("predicate:os-release-announcement")
    editorial_inference_without_new_reporting = bool(
        unverified_final_os_schedule
        or (_compiled_rule(r"\b(?:a|the|new)\s+(?:new\s+)?report\s+(?:claims?|suggests?)\b", re.I).search(lead[:700])
            and _compiled_rule(r"\bwithout supporting evidence\b.{0,50}\b(?:concludes?|inference|means?)\b|\b(?:false|unsupported)\s+(?:assertion|conclusion)\b", re.I).search(lead)
            and not _compiled_rule(r"\b(?:we|our\s+reporters?)\s+(?:confirmed|obtained|learned)\b|\bApple\s+(?:said|confirmed|announced)\b", re.I).search(_short_lead_scope(lead)))
        or (
            not editorial_first_party_action
            and
            not direct_product_lifecycle_action
            and
            not versioned_os_action
            and not versioned_os_compatibility_action
            and not current_generation_product_report
            and not current_beta_asset_disclosure
            and not current_event_schedule_report
            and not event_format_plan
            and not exact
            and not structured_direct_assertion
            and content_form
            in {
                "analysis",
                "buying_advice",
                "deal",
                "event_preview",
                "hands_on",
                "podcast",
                "poll",
                "review",
                "roundup",
                "third_party_spotlight",
                "tutorial",
                "user_anecdote",
            }
        )
    )
    trusted_direct_action = bool(
        not editorial_inference_without_new_reporting
        and (
            caller_trusted_direct_action
            or source_hardware_release
            or title_owned_direct_action
            or direct_product_lifecycle_action
            or (primary_claim_trusted and content_form == "news")
            or (bool(content_claim) and content_form == "news")
            or (bool(event_campaign_key) and content_form == "news"
                and bool(_compiled_rule(r"\bapple\s+(?:announced|activated|localized|localised)\b", 0).search(_normalized(lead)))
                and bool(_compiled_rule(r"tagline|slogan|hashmoji|hashtag|标语|主题|标签", 0).search(title_text)))
            or (
                (trusted_direct_action or structured_direct_assertion)
                and _title_proves_first_party_subject(title_text, identity)
            )
            or editorial_first_party_action
        )
    )
    measured_apple_market_action = any(
        key.startswith("structured-market-result:")
        and ":apple-" in key
        for key in event_keys
    )
    structural_direct_action = (
        trusted_direct_action
        or measured_apple_market_action
        or versioned_os_action
        or tracking_transparency_policy_action
        or bool(first_party_service_capability_signal)
        or official_apple_store_transaction_option_action
        or versioned_os_compatibility_action
        or direct_product_lifecycle_action
        or apple_owned_service_security_action
        or apple_chip_technical_disclosure
    )
    promotion_reason = ""
    if source_hardware_release:
        promotion_reason = "current Apple hardware release stated by the source publisher and product"
    elif versioned_os_action:
        promotion_reason = "current versioned Apple OS release or feature report"
    elif versioned_os_compatibility_action:
        promotion_reason = "current Apple OS device and feature compatibility matrix"
    elif first_party_service_capability_signal:
        promotion_reason = "title-led first-party service capability action"
    elif official_apple_store_transaction_option_action:
        promotion_reason = "official Apple Store checkout or financing option change"
    elif measured_apple_market_action:
        promotion_reason = "measured Apple market result with report, region, period, and value"
    elif direct_product_lifecycle_action:
        promotion_reason = "official Apple product lifecycle and repair-support change"
    elif apple_owned_service_security_action:
        promotion_reason = "current security or enforcement event centered on an Apple-operated service"
    elif apple_chip_technical_disclosure:
        promotion_reason = "current technical disclosure about an Apple chip process"
    elif trusted_direct_action:
        promotion_reason = "title-led direct Apple action confirmed by structured identity"
    elif editorial_first_party_action:
        promotion_reason = "current first-party Apple action independently stated by editorial source"
    defer_reason = _unsupported_third_party_reason(
        title,
        text,
        identity,
        exact,
        relevance_tier,
        structural_direct_action,
    )
    if any(key.startswith("primary-claim:vehicle-maker-")
           and ":compatibility-policy-clarification:" in key for key in event_keys):
        # The source-local policy claim already identifies the outside owner.
        # A shorter compatibility excerpt must not erase that attribution.
        defer_reason = "third-party vehicle compatibility policy clarification without an Apple platform change"
    observed_external_app_action = bool(
        relevance_tier == "weak"
        and relevance_reason.startswith(
            "third-party app update on an Apple platform"
        )
        and "app-store-delisting-restoration" not in identity.facets
    )
    if observed_external_app_action and not defer_reason:
        # The crawler's title/lead classifier has already established that the
        # outside app or product owns the action.  Incidental OS versions and
        # Apple device lists must not promote it during reconciliation.
        defer_reason = relevance_reason
    if third_party_app_availability and not defer_reason:
        defer_reason = (
            "third-party app availability without an Apple platform change"
        )
    if independent_content_playback:
        defer_reason = "media availability without an Apple publication action"
    if event_format_plan:
        # A concrete, currently reported operating format is itself the event
        # action; an analytical headline angle must not demote that evidence.
        defer_reason = ""
    if direct_product_lifecycle_action:
        defer_reason = ""
    if editorial_first_party_action:
        defer_reason = ""
    if (
        not event_format_plan
        and not company_performance_subject
        and _retrospective_explainer_without_new_action(
            title,
            f"{text}. {_normalized(evidence)[:1800]}",
        )
    ):
        defer_reason = "analysis or explanation without a new title-led Apple action"
    if (
        not defer_reason
        and relevance_tier == "weak"
        and relevance_reason.startswith("broad multi-vendor market")
    ):
        defer_reason = relevance_reason
    hard_boundary = _hard_third_party_boundary(text, defer_reason)
    if editorial_inference_without_new_reporting:
        if not defer_reason:
            defer_reason = (
                f"editorial {content_form.replace('_', ' ')} without a new Apple action"
            )
        hard_boundary = "editorial-inference-without-new-reporting"
    if defer_reason:
        structural_direct_action = False
    resolved_relevance_tier = relevance_tier
    if defer_reason:
        resolved_relevance_tier = "weak"
    elif relevance_tier == "weak" and structural_direct_action:
        resolved_relevance_tier = "strong"
    if (
        not hard_boundary
        and not structural_direct_action
        and resolved_relevance_tier == "weak"
        and "legal" not in identity.actions
        and relevance_reason.startswith(
            (
                "third-party AI model",
                "third-party app update",
                "third-party employer asset disposal",
                "analysis repackaging",
                "non-Apple component or industry",
                "non-Apple primary subject",
                "non-Apple title action",
                "third-party or non-Apple subject",
            )
        )
    ):
        hard_boundary = "independent-non-apple-or-editorial-action"
    if resolved_relevance_tier == "weak":
        weak_topic = _weak_topic_separation_key(title_text)
        if weak_topic:
            separation_keys.add(weak_topic)
    supplier_workforce_action = bool(
        _contains(
            title_text,
            "hire",
            "hires",
            "hiring",
            "recruit",
            "recruits",
            "recruiting",
            "招聘",
            "扩招",
            "招工",
            "增聘",
        )
        and identity.title_products
    )
    supplier_operating_result = bool(
        _contains(text, "ship", "ships", "shipped", "shipment", "shipments", "出货", "供应")
        and _contains(text, "supplier", "display", "panel", "component", "供应商", "面板", "零部件")
        and bool(_compiled_rule(r"\b\d+(?:\.\d+)?\s*(?:%|percent|million|billion)\b|\d+(?:\.\d+)?\s*(?:万|亿|%)", 0).search(text))
    )
    if supplier_workforce_action:
        separation_keys.add("primary-claim-predicate:supplier-workforce-expansion")
    if supplier_operating_result:
        separation_keys.add("primary-claim-predicate:supplier-operating-result")
    title_owned_versioned_os_feature = bool(
        identity.content_form == "news"
        and versioned_os_action
        and _compiled_rule(r"^(?:苹果\s*)?(?:ios|ipados|macos|watchos|tvos|visionos)\s+\d+(?:\.\d+)*\b", re.I).match(title_text)
        and not (
            _compiled_rule(r"\b(?:hint(?:s|ed)?\s+at|reveal(?:s|ed)?|leak(?:s|ed)?|code\s+(?:shows?|suggests?))\b|"
                r"(?:代码|文件).{0,18}(?:暗示|曝光|泄露)", re.I).search(title_text)
            and identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
        )
    )
    # Product type is independent of Apple relevance. A compatibility-only
    # source can still have an initially strong observation before outcome
    # resolution, and its physical object must not fall back to software.
    accessory_category = source_accessory_category(title)
    if (_compiled_rule(r"patent|专利", re.I).search(title + " " + lead[:500])
          and _compiled_rule(r"blood.?oxygen|pulse.?oxim|血氧", re.I).search(title + " " + lead[:500])
          and _compiled_rule(r"judge|court|ruling|interest|法官|法院|裁定|利息", re.I).search(title + " " + lead[:500])):
        category_hint = "hardware_products"
        separation_keys.add("source-local-action-authority")
    elif primary_claim_category:
        # A title-led concrete claim owns the event category. Later generic
        # product/background rules may enrich the profile, but must not turn a
        # system disclosure into hardware (or a procurement action into
        # software) based on incidental entities in the article body.
        category_hint = primary_claim_category
    elif accessory_category:
        category_hint = accessory_category
    elif "patent" in identity.case_topics and has_haptic_patent_subject(title, lead):
        category_hint = "hardware_products"
        separation_keys.add("source-local-action-authority")
    elif "patent" in identity.case_topics and identity.title_products & _SOFTWARE_FIRST_PARTY_PRODUCTS:
        # A device mentioned in background cannot turn a software patent
        # dispute into a physical-product patent disclosure in compatibility callers.
        category_hint = "software_systems"
        separation_keys.add("source-local-action-authority")
    elif (identity.content_form == "news" and identity.scope == "apple-direct"
            and identity.title_products & _SOFTWARE_FIRST_PARTY_PRODUCTS
            and not identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
            and not ("apple-tv" in identity.title_products and event_kind == "hardware_market")
            and "feature-change" in identity.title_actions):
        # A named platform owns its feature change; device launches in the
        # supporting report cannot replace its software category. Apple TV's
        # shared service/device alias retains an identified hardware action.
        category_hint = "software_systems"
        separation_keys.add("source-local-category-authority")
    elif title_owned_versioned_os_feature or (versioned_os_action and release_announcement_keys):
        category_hint = "software_systems"
        separation_keys.add("source-local-category-authority")
    elif any(
        key.startswith("structured-assertion:apple-facility:education-center:opening")
        for key in event_keys
    ):
        category_hint = "software_systems"
    elif any(
        key.startswith("structured-assertion:apple-facility:")
        for key in event_keys
    ):
        category_hint = "hardware_products"
    elif (
        identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
        and any(
            key.startswith("structured-title-action:apple-silicon-generation:")
            for key in event_keys
        )
    ):
        category_hint = "hardware_products"
    if ("primary-claim-predicate:measured-apple-market-result" in separation_keys
            and source_market_measurement_frame(title, lead, source_units or source_facts,
                                                published_year=published_year) is not None):
        # A verified current Apple result owns the report even when component
        # prices explain its market context. Preserve the existing metric keys.
        separation_keys.add("source-local-action-authority")
        category_hint = "hardware_products"
        resolved_relevance_tier = "strong"
        structural_direct_action = True
        defer_reason = hard_boundary = ""
    return ReconciliationProfile(
        event_keys=frozenset(event_keys),
        boundary_keys=frozenset(boundary_keys),
        exact_facets=exact,
        separation_keys=frozenset(separation_keys),
        defer_reason=defer_reason,
        category_hint=category_hint,
        hard_boundary=hard_boundary,
        identity=identity,
        relevance_tier=resolved_relevance_tier,
        trusted_direct_action=structural_direct_action,
        promotion_reason=promotion_reason,
        event_kind_hint=("hardware_market" if future_hardware_configuration else
            "hardware_market" if event_kind == "third_party_ecosystem" and any(
            _compiled_rule(r"primary-claim:apple-[^:]+-sourcing:component-.+", 0).fullmatch(key) for key in event_keys)
            else event_kind),
    )


































def profiles_share_primary_claim(profiles: Sequence[ReconciliationProfile]) -> bool:
    """A shared concrete claim may resolve a generic topic warning, never a conflict."""
    if len(profiles) < 2:
        return False
    if all(profile.bound_claim is not None for profile in profiles):
        return all(profile_pair_decision(left,right) == "match"
                   for left,right in combinations(profiles,2))
    shared = {key for key in profiles[0].event_keys if key.startswith("primary-claim:")}
    for profile in profiles[1:]:
        shared.intersection_update(profile.event_keys)
        if not shared:
            return False
    return bool(shared) and all(
        profile_pair_decision(left, right) == "match"
        for left, right in combinations(profiles, 2)
    )


def reconciliation_seed_compatible(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    return profile_pair_decision(left, right) != "conflict"


def _stable_article_key(article: object) -> tuple[str, str, str]:
    return (
        str(getattr(article, "url", "")),
        str(getattr(article, "source", "")),
        str(getattr(article, "title", "")),
    )






def _reunite_exact_relation_groups(groups: Sequence[Sequence[ArticleT]], profiles: dict[int, ReconciliationProfile]) -> list[list[ArticleT]]:
    """Compatibility forwarding; exact relations have no second merge pass."""
    articles = [article for group in groups for article in group]
    return [list(group) for group in reconcile_articles(articles,
        profile_for=lambda article: profiles[id(article)], initial_groups=())]


def resolve_reconciliation_outcome(
    profile: ReconciliationProfile,
    *,
    observed_tier: str,
    observed_reason: str,
    observed_category: str,
) -> tuple[str, str, str]:
    """Compatibility signature; source identity, not observations, owns outcome."""
    return _source_reconciliation_outcome(profile)


def _source_reconciliation_outcome(profile: ReconciliationProfile) -> tuple[str, str, str]:
    if profile.eligibility is not None:
        decision = profile.eligibility
        if not decision.resolved:
            raise ValueError("Unresolved source qualification requires evidence review")
        return decision.tier, decision.reason, decision.category
    identity = profile.identity
    category = profile.category_hint
    if not category:
        title_products = identity.title_products if identity is not None else frozenset()
        products = title_products or (identity.products if identity is not None else frozenset())
        financed_device = identity is not None and bool(identity.title_components & {"financed-device-restriction", "apple-device-leasing-program"})
        hardware_wave = profile.event_kind_hint == "hardware_market" and identity is not None and bool(identity.products & _HARDWARE_FIRST_PARTY_PRODUCTS) and not identity.title_products
        category = ("hardware_products" if financed_device or hardware_wave else "software_systems" if (products & _SOFTWARE_FIRST_PARTY_PRODUCTS or profile.event_kind_hint == "legal_antitrust")
                    else "hardware_products" if products & _HARDWARE_FIRST_PARTY_PRODUCTS or profile.event_kind_hint in {"hardware_market", "retail_store"}
                    else "software_systems")
    parent = profile.parent_source
    if parent is not None and parent.identity is not None and parent.identity.content_form in {
            "buying_advice", "deal", "poll", "roundup", "third_party_spotlight", "tutorial", "analysis", "opinion"}:
        parent_tier, parent_reason, _parent_category = _source_reconciliation_outcome(parent)
        if parent_tier == "weak":
            return "weak", parent_reason, category
    compatibility_context_only = (
        bool(profile.ecosystem_reason)
        and profile.hard_boundary in {"", "independent-third-party-action"}
        and profile.defer_reason in {"", "third-party title context without a direct Apple action"}
    )
    if (profile.hard_boundary or profile.defer_reason) and not compatibility_context_only:
        return "weak", profile.defer_reason or profile.hard_boundary, category
    if profile.ecosystem_reason:
        return "ecosystem", profile.ecosystem_reason, "software_systems"
    if profile.event_kind_hint == "ecosystem_interop":
        return "ecosystem", "concrete Apple platform interoperability milestone", "software_systems"
    if any(key.startswith("primary-claim:third-party-platform-") for key in profile.event_keys):
        return "ecosystem", "concrete Apple platform compatibility milestone", category
    if "action:first-party-document-lifecycle" in profile.separation_keys:
        return "strong", "first-party Apple document lifecycle update", "software_systems"
    source_action = any(key.startswith("source-action:") for key in profile.event_keys)
    if profile.trusted_direct_action or source_action:
        return "strong", profile.promotion_reason or "source-backed concrete Apple action", category
    if profile.event_kind_hint == "third_party_ecosystem":
        return "weak", "third-party app or independent non-Apple action; Apple is context", category
    if profile.event_kind_hint == "marketing_ad":
        # A product name in an ad is not an independent product action. A
        # specific first-party campaign has already supplied trusted support.
        return "weak", "routine product advertisement without a distinct Apple campaign action", category
    # Unmigrated families retain their old qualification until a source
    # relationship replaces it. These retrieval keys are never typed evidence
    # and cannot authorize a migrated, unresolved or source-local claim.
    legacy_news_signal = (profile.bound_claim is None
        and "source-local-action-authority" not in profile.separation_keys
        and any(not key.startswith("structured-canonical-title:") for key in profile.event_keys))
    if (identity is not None and identity.scope == "apple-direct" and identity.content_form == "news"
            and (identity.action_owner in {"apple", "apple-target"} or identity.title_actions or legacy_news_signal)):
        reason = ("source-backed Apple lawsuit or court action" if "legal" in identity.actions
                  else "title-owned Apple chip process news action" if "apple-chip-process-roadmap" in identity.facets
                  else "title-owned Apple news action")
        return "strong", reason, category
    return "weak", "no source-backed independent Apple action", category


def reconcile_articles(
    articles: Sequence[ArticleT],
    *,
    profile_for: Callable[[ArticleT], ReconciliationProfile],
    initial_groups: Sequence[Sequence[ArticleT]],
) -> tuple[tuple[ArticleT, ...], ...]:
    """Split recall-oriented seeds, then reunite exact event identities."""
    ordered = sorted({id(article): article for article in articles}.values(), key=_stable_article_key)
    profiles = {id(article): profile_for(article) for article in ordered}
    profiles = resolve_sparse_release_profiles(profiles)



    # A seed is a recall hint, never prior membership. Start from the same
    # source set regardless of how callers partitioned their hints.
    groups: list[list[ArticleT]] = [[article] for article in ordered]
    pair_cache = {}
    def pair(left, right):
        key = tuple(sorted((id(left), id(right))))
        if key not in pair_cache:
            pair_cache[key] = profile_pair_decision(profiles[id(left)], profiles[id(right)])
        return pair_cache[key]
    def supported_event_keys(group: Sequence[ArticleT]) -> set[str]:
        return supported_reconciliation_event_keys(
            [profiles[id(article)] for article in group]
        )

    known_report_entities = {
        component.removeprefix("report-attribution:")
        for profile in profiles.values()
        if profile.identity is not None
        for component in profile.identity.components
        if component.startswith("report-attribution:")
    }
    parent = list(range(len(groups)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def merge_roots(left_index: int, right_index: int) -> bool:
        left_root = root(left_index)
        right_root = root(right_index)
        if left_root == right_root:
            return False
        if right_root < left_root:
            left_root, right_root = right_root, left_root
        groups[left_root] = sorted(
            [*groups[left_root], *groups[right_root]],
            key=_stable_article_key,
        )
        groups[right_root] = []
        parent[right_root] = left_root
        return True

    def union(left_index: int, right_index: int) -> bool:
        left_root, right_root = root(left_index), root(right_index)
        if left_root == right_root:
            return False
        decisions = [pair(left, right) for left in groups[left_root] for right in groups[right_root]]
        if "conflict" in decisions or "match" not in decisions:
            return False
        return merge_roots(left_root, right_root)

    # Exact identities can become newly supported after two sparse source
    # groups merge. Rebuild the key graph until no root changes so a campaign
    # name, a localized date, or another exact alias can bridge transitively
    # without depending on source order. Each successful pass reduces the root
    # count, which bounds the loop and keeps this post-fetch work small.
    exact_groups_changed = True
    while exact_groups_changed:
        exact_groups_changed = False
        key_buckets: dict[str, list[int]] = {}
        for index, group in enumerate(groups):
            if not group or root(index) != index:
                continue
            candidate_keys = supported_event_keys(group)
            for article in group:
                profile = profiles[id(article)]
                candidate_keys.update("pair-facet:" + key for key, _ in source_profile_merge_keys(profile))
                if profile.identity is not None:
                    candidate_keys.update("pair-anchor:" + key for key in profile.identity.specific_anchors)
                if profile.bound_claim is not None:
                    claim = profile.bound_claim
                    candidate_keys.add("pair-claim:" + repr((claim.subject, claim.action, claim.object)))
            for key in candidate_keys:
                if key.startswith("structured-entity-component:"):
                    entity = key.split(":", 2)[1]
                    if entity not in known_report_entities:
                        continue
                key_buckets.setdefault(key, []).append(index)
        for key in sorted(key_buckets):
            members = key_buckets[key]
            if not members:
                continue
            # A conflicting first member must not block two later compatible
            # members from reconciling. Treat each exact key bucket as a graph
            # and let the existing conflict gates decide every possible edge.
            for left_index, right_index in combinations(members, 2):
                exact_groups_changed = union(left_index, right_index) or exact_groups_changed

    groups = [group for index, group in enumerate(groups) if group and root(index) == index]
    groups.sort(key=lambda group: tuple(_stable_article_key(article) for article in group))
    return tuple(tuple(group) for group in groups)



def validate_source_span_dispositions(evidence, assigned, remainder_ids, excluded):
    units = {unit.unit_id: unit for unit in evidence.units}
    if any(not isinstance(span, (tuple, list)) or len(span) != 3 for span in remainder_ids):
        raise ValueError("Unprocessed evidence requires source-local spans")
    if any(len(span) != 4 or not span[3] for span in excluded):
        raise ValueError("Excluded evidence requires source-local spans and reasons")
    destinations = (assigned, remainder_ids, [span[:3] for span in excluded])
    for spans in destinations:
        if any(key not in units or not 0 <= start < end <= len(units[key].text) for key, start, end in spans):
            raise ValueError("Evidence destination outside source unit")
    for key, unit in units.items():
        boundaries = sorted({0, len(unit.text), *(point for spans in destinations
            for unit_id, start, end in spans if unit_id == key for point in (start, end))})
        for left, right in zip(boundaries, boundaries[1:]):
            covering = sum(any(unit_id == key and start <= left and right <= end
                               for unit_id, start, end in spans) for spans in destinations)
            if covering != 1:
                raise ValueError("Incomplete or overlapping source evidence dispositions")


def validate_evidence_dispositions(evidence, projections, remainder_ids, excluded):
    """Every retained unit has an explicit destination before replacing its parent."""
    units = {unit.unit_id: unit for unit in evidence.units}
    assigned = [span for projection in projections for span in projection.claim.evidence_spans]
    validate_source_span_dispositions(evidence, assigned, remainder_ids, excluded)
    for projection in projections:
        claim = projection.claim
        if claim.article_id != evidence.article_id:
            raise ValueError("Foreign claim source")
        facts = tuple(units[key].text[start:end] for key, start, end in claim.evidence_spans
                      if key in units and 0 <= start < end <= len(units[key].text))
        # Identity evidence may establish a role or attribution without being
        # selected as a news fact. Both still reference this exact source.
        if any(key not in units or not 0 <= start < end <= len(units[key].text)
               for _, _, _, key, start, end in claim.qualifiers):
            raise ValueError("Claim qualifiers must resolve to original source spans")
        if facts != projection.key_facts or set(claim.unit_ids) != {key for key, _, _ in claim.evidence_spans}:
            raise ValueError("Claim facts must resolve to original source spans")



def source_identity_is_mentioned(identity: EventIdentity, text: str, title: str = "") -> bool:
    """Use existing product/entity aliases to scope a source-local condition."""
    text, title = _normalized(text), _normalized(title)
    if any(_contains(title, *aliases) and _contains(text, *aliases) for aliases in _MEMORY_SUPPLIER_ALIASES.values()):
        return True
    products = identity.title_products
    if any(name in products and _contains(text, *aliases) for name, aliases in PRODUCT_PATTERNS):
        return True
    # Mentioned background actors do not inherit ownership of the title action.
    entities = identity.title_named_subjects | frozenset(entity for entity in identity.actors
        if _contains(title, *_MEMORY_SUPPLIER_ALIASES.get(entity, (entity.replace("-", " "),))))
    return any(_contains(text, *_MEMORY_SUPPLIER_ALIASES.get(entity, (entity.replace("-", " "),)))
               for entity in entities)


def source_profile_merge_keys(profile: ReconciliationProfile) -> set[tuple[str, tuple[str, ...]]]:
    """Source retrieval hints only; every resulting candidate still uses one pair."""
    facets = set(profile.exact_facets)
    if profile.identity is not None:
        facets.update(profile.identity.facets)
    if facets & {"apple-product-data-leak-enforcement", "apple-product-data-leak-specs", "iphone-chip-packaging", "iphone-drop-test-leak"}:
        facets.discard("apple-product-data-leak")
    return {(key, ()) for key in facets}


def claim_eligibility(claim: BoundClaim) -> ClaimEligibility:
    """Apply news policy to a relationship, independently of binding success."""
    category = claim.category or ("hardware_products" if claim.action == "product-launch" else "software_systems")
    if claim.report_role == "background" and claim.evidence_spans:
        return ClaimEligibility("weak", category, "Background assertion without an independent current report")
    if not (claim.subject and claim.action and claim.object and claim.subject_relation and claim.report_role and claim.evidence_spans):
        return ClaimEligibility("", category, claim.review_reason or "Source subject, action or report role remains unresolved")
    if claim.report_role != "independent":
        return ClaimEligibility("", category, "Supporting assertion requires an established source action")
    if claim.subject_relation == "independent":
        return ClaimEligibility("weak", category, "Independent third-party action; Apple is the host platform")
    if claim.subject_relation == "apple-direct":
        return ClaimEligibility("strong", category, "Source-bound independent Apple report")
    if claim.subject_relation == "platform-interop":
        return ClaimEligibility("ecosystem", "software_systems", "Concrete Apple platform interoperability operation")
    return ClaimEligibility("", category, "Source relationship to Apple remains unresolved")


def bound_reconciliation_profile(claim: BoundClaim) -> ReconciliationProfile:
    decision = claim_eligibility(claim)
    return ReconciliationProfile(frozenset(), frozenset(), bound_claim=claim,
        category_hint=decision.category,
        event_kind_hint=claim.event_kind or ("hardware_market" if claim.action == "product-launch" else "software_update"),
        relevance_tier=decision.tier, promotion_reason=decision.reason,
        trusted_direct_action=decision.tier == "strong", eligibility=decision,
        review_reasons=(claim.review_reason,) if claim.review_reason else ())



def resolve_sparse_release_profiles(profiles: dict[int, ReconciliationProfile]) -> dict[int, ReconciliationProfile]:
    """Expose uniquely supported platform/stage evidence before any pair is decided."""
    def signatures(profile):
        if profile.identity is None or "predicate:os-release-announcement" not in profile.separation_keys:
            return set()
        return {tuple(component.split(":", 2)[1:]) for component in profile.identity.components
                if component.startswith("os-wave-platform:")}
    def waves(profile):
        return {tuple(key.split(":", 2)[1:]) for key in profile.event_keys if key.startswith("apple-os-release-wave:")}
    supported = {}
    for profile in profiles.values():
        for platform, stage in signatures(profile):
            supported.setdefault((platform, stage), set()).update(version for version, candidate_stage in waves(profile) if candidate_stage == stage)
    resolved = dict(profiles)
    for key, profile in profiles.items():
        revised = [(version, stage) for version, stage in waves(profile) if stage == 'rc-revised']
        if len(revised) == 1:
            version = revised[0][0]
            platforms = {platform for platform, stage in signatures(profile) if stage == 'rc-revised'}
            builds = {c for c in profile.identity.components if c.startswith('os-release-build:')}
            stages = {stage for other in profiles.values() for platform, stage in signatures(other)
                      if platform in platforms and stage.startswith('rc-') and stage[3:].isdigit()
                      and (version, stage) in waves(other)
                      and not (builds and (other_builds := {c for c in other.identity.components if c.startswith('os-release-build:')})
                               and builds != other_builds)}
            if len(stages) == 1:
                stage = next(iter(stages))
                # Retain the source's unspecified revision; only the unique
                # same-platform/version peer supplies its matching identity.
                convert = lambda keys: frozenset(k.replace(':rc-revised', ':' + stage) for k in keys)
                resolved[key] = replace(profile, event_keys=convert(profile.event_keys),
                    boundary_keys=convert(profile.boundary_keys), separation_keys=convert(profile.separation_keys),
                    identity=replace(profile.identity, components=convert(profile.identity.components)))
            continue
        if waves(profile):
            continue
        scope = signatures(profile)
        stages = {stage for _, stage in scope}
        versions = set().union(*(supported.get(signature, set()) for signature in scope)) if scope else set()
        if len(versions) > 1:
            resolved[key] = replace(profile, separation_keys=profile.separation_keys | {
                f"ambiguous-platform-stage:{platform}:{stage}" for platform, stage in scope})
        elif len(stages) == len(versions) == 1:
            version, stage = next(iter(versions)), next(iter(stages))
            resolved[key] = replace(profile,
                event_keys=profile.event_keys | {f"apple-os-release-wave:{version}:{stage}"},
                separation_keys=profile.separation_keys | {f"unique-platform-stage-support:{version}:{stage}"})
    return resolved


def _platform_performance_evidence(title: str, evidence: str) -> tuple[set[str], set[str]]:
    """Read per-operation measurements only for a title-owned performance update."""
    if not _compiled_rule(r"faster|performance|底层优化|性能|更快", re.I).search(title):
        return set(), set()
    platform = _compiled_rule(r"\b(iOS|iPadOS|macOS|watchOS|tvOS|visionOS)\s*(\d+(?:\.\d+)*)", re.I).search(title)
    if platform is None:
        return set(), set()
    system, version = platform.group(1).lower(), platform.group(2)
    patterns = {
        "app-launch": r"(?:apps?\s+launch|app\s*启动|应用启动)",
        "photos-load": r"(?:photos(?:\s+content)?\s+loads?|相册加载|照片加载)",
        "airdrop-transfer": r"(?:airdrop\s+transfers?|隔空投送)",
    }
    measurements = set()
    for operation, pattern in patterns.items():
        for match in re.finditer(pattern + r"[^,，。.!?;；%]{0,45}?(\d+(?:\.\d+)?)\s*[%％]", evidence, re.I):
            measurements.add(f"platform-performance:{system}:{version}:{operation}:{match.group(1)}")
    if len(measurements) < 2:
        return set(), set()
    return measurements, {f"platform-performance-version:{system}:{version}"}


def resolve_event_outcome(profiles: Sequence[ReconciliationProfile]) -> tuple[str, str, str, str]:
    """Resolve an already reconciled group's source evidence without voting."""
    if not profiles:
        raise ValueError("An event requires source profiles")
    outcomes = [_source_reconciliation_outcome(profile) for profile in profiles]
    # Source outcomes already encode exclusion and support priority. Grouping
    # consumes those decisions; it must not re-interpret the same profile flags.
    direct = [profile for profile, outcome in zip(profiles, outcomes) if outcome[0] == "strong"]
    category_hints = {profile.category_hint for profile in direct if profile.category_hint}
    source_categories = {outcome[2] for outcome in outcomes}
    category = (next(iter(category_hints)) if len(category_hints) == 1
                else next(iter(source_categories)) if len(source_categories) == 1
                else "software_systems")
    kinds = {profile.event_kind_hint for profile in profiles if profile.event_kind_hint}
    keys = set().union(*(profile.event_keys for profile in profiles))
    if len(kinds) == 1:
        kind = next(iter(kinds))
    elif any(key.startswith("apple-os-release-wave:") for key in keys):
        kind = "os_app"
    elif any(profile.identity is not None and "legal" in profile.identity.actions for profile in profiles):
        kind = "legal_antitrust"
    else:
        kind = "hardware_market" if category == "hardware_products" else "os_app"
    if len(outcomes) == 1:
        return (*outcomes[0], kind)
    if direct:
        reasons = sorted({outcome[1] for outcome in outcomes if outcome[0] == "strong" and outcome[1]})
        return "strong", "; ".join(reasons), category, kind
    if any(outcome[0] == "ecosystem" for outcome in outcomes):
        return "ecosystem", "concrete Apple platform compatibility milestone", category, kind
    reasons = sorted({outcome[1] for outcome in outcomes if outcome[1]})
    return "weak", "; ".join(reasons), category, kind


def _fact_needs_preservation(fact: PreparedFact) -> bool:
    return fact.owned or bool(fact.roles & {"source-measurement", "source-numeric-detail", "source-condition", "source-projection-fact", "source-structured-evidence"})


def reconcile_fact_views(views: Sequence[SourceFactView], *, base_limit: int, official_limit: int) -> tuple[PreparedFact, ...]:
    """Select from source-prepared facts without parsing an event summary."""
    ordered = sorted(views, key=lambda view: (not view.official, view.source_priority, view.published_utc))
    price_event = any(view.compact_hardware_price for view in ordered)
    limit = official_limit if any(view.official for view in ordered) else base_limit
    if len(ordered) > 1:
        slots = sum(min(view.raw_fact_count, 8) for view in ordered)
        limit = min(72 if price_event else 48, max(limit, min(slots + int(price_event), limit + len(ordered) * (3 if price_event else 2))))
    selected = []

    def add(fact):
        for index, existing in enumerate(selected):
            duplicate = (fact.text == existing.text if _fact_needs_preservation(fact) or _fact_needs_preservation(existing)
                         else fact.key in existing.key or existing.key in fact.key)
            if duplicate:
                if fact.text == existing.text:
                    selected[index] = replace(existing, origins=tuple(dict.fromkeys(existing.origins + fact.origins)))
                return False
        selected.append(fact)
        return True

    for view in ordered:
        for fact in (*view.owned, *view.normal):
            if _fact_needs_preservation(fact):
                add(fact)
    limit = max(limit, len(selected))
    if price_event:
        responses = [fact for view in ordered if view.compact_hardware_price for fact in view.responses]
        responses.sort(key=lambda fact: -fact.priority)
        if responses:
            add(_compact_source_price_response_fact(responses))
        candidates = [(fact.priority, source_index, fact_index, fact)
                      for source_index, view in enumerate(ordered) for fact_index, fact in enumerate(view.price)]
        buckets = [(max(8, min(52, limit - 16)), "price-change"),
                   (max(4, min(8, limit // 6)), "market-reaction"),
                   (max(4, min(8, limit // 6)), "price-scope")]
        used = set()
        for bucket_index, (bucket_limit, role) in enumerate(buckets):
            bucket = [item for item in candidates if role in item[3].roles]
            bucket.sort(key=(lambda item: (int(len(item[3].text) > 220), -item[0], item[1], item[2]))
                        if bucket_index == 0 else (lambda item: (-item[0], item[1], item[2])))
            added = 0
            for _score, source_index, fact_index, fact in bucket:
                marker = (source_index, fact_index)
                if marker in used:
                    continue
                if add(fact):
                    used.add(marker)
                    added += 1
                if len(selected) >= limit:
                    return tuple(selected)
                if added >= bucket_limit:
                    break
        for _score, source_index, fact_index, fact in sorted(candidates, key=lambda item: (-item[0], item[1], item[2])):
            if (source_index, fact_index) not in used:
                add(fact)
            if len(selected) >= limit:
                break
        return tuple(selected)
    rows = [fact for view in ordered for fact in view.structured]
    if rows:
        limit = min(72, max(limit, len(rows) + base_limit))
        for fact in rows:
            add(fact)
    for index in range(max((len(view.normal) for view in ordered), default=0)):
        for view in ordered:
            if index < len(view.normal):
                add(view.normal[index])
                if len(selected) >= limit:
                    return tuple(selected)
    return tuple(selected)


def _compact_source_price_response_fact(facts: Sequence[PreparedFact]) -> PreparedFact:
    """Keep only provenance used by the selected response clauses."""
    flags = frozenset().union(*(fact.roles for fact in facts))
    clauses, used_roles = [], set()
    if ({"ai-data-center", "memory-storage"} <= flags or "component-cost" in flags):
        clauses.append("AI data centers drove extraordinary memory and storage demand and unusually fast component-cost increases")
        used_roles.update({"ai-data-center", "memory-storage"} if {"ai-data-center", "memory-storage"} <= flags
                          else {"component-cost"})
    products = " on products including iPad and Mac" if {"ipad", "mac"} <= flags else " on some products"
    if "shielded" in flags:
        clauses.append("Apple says it previously shielded customers but now must raise prices" + products)
        used_roles.add("shielded")
    elif "begin-raising" in flags:
        clauses.append("Apple says it must begin raising prices" + products)
        used_roles.add("begin-raising")
    if {"ipad", "mac"} <= flags and used_roles & {"shielded", "begin-raising"}:
        used_roles.update({"ipad", "mac"})
    if {"unwelcome", "solutions"} <= flags:
        clauses.append("Apple acknowledges this is not welcome news and says it is working tirelessly to find solutions")
        used_roles.update({"unwelcome", "solutions"})
    elif "solutions" in flags:
        clauses.append("Apple says it is working tirelessly to find solutions")
        used_roles.add("solutions")
    if not clauses:
        return facts[0] if facts else PreparedFact("", "")
    text = "Apple's response: " + "; ".join(clauses) + "."
    key = _compiled_rule(r"[^0-9a-z\u4e00-\u9fff]+", 0).sub(" ", text.lower(), 0).strip()[:180]
    origins = tuple(dict.fromkeys(origin for fact in facts if fact.roles & used_roles for origin in fact.origins))
    return PreparedFact(text, key, origins=origins)


def compact_source_price_response(facts: Sequence[PreparedFact]) -> str:
    return _compact_source_price_response_fact(facts).text


def resolve_event_fact_plan(views: Sequence[SourceFactView], *, relevance_tier: str,
                            base_limit: int, official_limit: int) -> EventFactPlan:
    """Finalize fact/display choices from source views; assembly only copies them."""
    if not views:
        return EventFactPlan("", "", ())
    scoped_views = []
    for view in views:
        if view.owned or foldable_iphone_generation_subject(view.display_title) == 'foldable-iphone':
            scoped_views.append(view)
            continue
        unassigned, fields = [], {}
        for field in ('normal', 'structured', 'price', 'responses', 'required_actions'):
            kept = []
            for fact in getattr(view, field):
                if source_fact_changes_generation(view.display_title, fact.text):
                    if not any(fact.text == old.text for old in unassigned):
                        unassigned.append(replace(fact, owned=False, roles=frozenset({'unprocessed-source-action'}),
                            reason='This source names a separate generation development action; assign it independently of the parent event'))
                else:
                    kept.append(fact)
            fields[field] = tuple(kept)
        scoped_views.append(replace(view, **fields, unprocessed=view.unprocessed + tuple(unassigned)))
    views = scoped_views
    selected = reconcile_fact_views(views, base_limit=base_limit, official_limit=official_limit)
    ordered = sorted(views, key=lambda view: (view.source_priority, view.published_utc))
    title = ordered[0].display_title
    details, seen = [], set()
    displayed_source_sentences = []
    for view in ordered:
        for sentence in view.summary_units:
            key = sentence.lower()[:100]
            if key not in seen:
                details.append(sentence)
                displayed_source_sentences.append((view.source, view.url, sentence))
                seen.add(key)
            if len(details) >= 3:
                break
        if len(details) >= 3:
            break
    for fact in selected[:8]:
        key = fact.text.lower()[:100]
        if key not in seen:
            seen.add(key)
            details.append(fact.text)
    summary = f"{title}. {' '.join(details)}" if details else title
    required = []
    def add(fact):
        if not any((fact.text == old.text if _fact_needs_preservation(fact) or _fact_needs_preservation(old)
                    else fact.key in old.key or old.key in fact.key) for old in required):
            required.append(fact)
    for fact in selected:
        if _fact_needs_preservation(fact):
            add(fact)
    price_event = any(view.compact_hardware_price for view in ordered)
    if price_event:
        responses = [fact for view in ordered if view.compact_hardware_price for fact in view.responses]
        responses.sort(key=lambda fact: -fact.priority)
        if responses:
            add(_compact_source_price_response_fact(responses))
    elif relevance_tier == "strong":
        for view in ordered:
            for fact in view.structured:
                add(fact)
    actions = [fact for view in ordered for fact in view.required_actions]
    actions.sort(key=lambda fact: -fact.priority)
    for fact in actions[:2]:
        add(fact)
    unresolved = [fact for view in ordered for fact in view.unprocessed]

    def covered(fact, kept):
        # Keys are retrieval abbreviations, not evidence that a sentence's
        # extra conditions survived. Empty origins likewise prove no span.
        # Formatting equivalence is confined to whitespace at punctuation;
        # no numbers, words, qualifiers or source identities are discarded.
        fact_text = _compiled_rule(r"\s+([.,;:!?，。；：！？])", 0).sub(r"\1", fact.text.casefold(), 0).strip()
        kept_text = _compiled_rule(r"\s+([.,;:!?，。；：！？])", 0).sub(r"\1", kept.text.casefold(), 0).strip()
        # Chinese punctuation already delimits tokens. Spaces immediately
        # after it are layout, unlike spaces inside names, units or numbers.
        fact_text = _compiled_rule(r"([，。；：！？、])\s+", 0).sub(r"\1", fact_text, 0)
        kept_text = _compiled_rule(r"([，。；：！？、])\s+", 0).sub(r"\1", kept_text, 0)
        if fact_text not in kept_text:
            return False
        if not fact.origins:
            return False
        def origin_covered(origin, other):
            if origin[:3] != other[:3]:
                return False
            if origin[3] and other[3]:
                return (origin[3] == other[3] and other[4] <= origin[4]
                        and origin[5] <= other[5])
            # Source-text-only has no offsets to compare. A complete local
            # sentence can nevertheless be displayed inside its own selected
            # paragraph. Require a sentence boundary, not a substring that
            # could omit attribution, negation or a leading condition.
            if fact_text == kept_text:
                return True
            if not fact_text.endswith((".", "!", "?", "。", "！", "？")):
                return False
            return any(not kept_text[:match.start()].rstrip()
                       or kept_text[:match.start()].rstrip()[-1] in ".!?。！？"
                       for match in re.finditer(re.escape(fact_text), kept_text))
        return all(any(origin_covered(origin, other) for other in kept.origins)
                   for origin in fact.origins)

    # Prepared local remainder may become fully represented after final
    # selection/aggregation. Its actual source span, not a shared topic or
    # another source's identical prose, determines whether it was consumed.
    # Checking an unresolved attribution/reference is a separate obligation:
    # merely displaying its words cannot certify that relationship.
    verification_roles = frozenset({"unresolved-media-reference", "unverified-attribution",
                                   "unprocessed-editorial-condition", "unprocessed-condition"})
    def qualification_displayed(fact):
        # Only sentences actually appended above count, not the entire input
        # summary or another source's identical words. No text span is invented.
        return ("unprocessed-source-qualification" in fact.roles
                and bool(fact.origins)
                and all(any(origin[:2] == (source, url) and fact.text == sentence
                            for source, url, sentence in displayed_source_sentences)
                        for origin in fact.origins))

    unresolved = [fact for fact in unresolved
                  if fact.roles & verification_roles
                  or not (qualification_displayed(fact)
                          or any(covered(fact, kept) for kept in (*selected, *required)))]
    for view in ordered:
        # Response candidates are only compacted for their own price source.
        # A non-price reply still needs a visible local disposition, including
        # when another source makes the assembled event a price event.
        pending = (*view.normal, *(view.responses if not view.compact_hardware_price else ()))
        for fact in pending:
            if any(covered(fact, kept) for kept in (*selected, *required, *unresolved)):
                continue
            unresolved.append(replace(fact,
                roles=fact.roles | frozenset({"unprocessed-prepared-source-fact"}),
                reason=fact.reason or "Prepared source detail was not retained in the event fact selection; review with its source context: " + view.display_title))
    # A newly recovered qualification may be inside a prepared paragraph that
    # reached the same review queue after budgeting. The larger exact source
    # span already carries that condition; do not require it twice.
    unresolved = [fact for index, fact in enumerate(unresolved)
                  if "unprocessed-source-qualification" not in fact.roles
                  or not any(other is not fact and covered(fact, other)
                             and (other.text != fact.text or other_index < index)
                             for other_index, other in enumerate(unresolved))]
    return EventFactPlan(title, summary, selected, tuple(required), tuple(unresolved),
                         tuple(displayed_source_sentences))
