"""Shared data contracts. No collection or editorial rules."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from .event_identity import EventIdentity

@dataclass
class Source:
    name: str
    default_tz: str
    feeds: list[str] = field(default_factory=list)
    wordpress_posts_apis: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    domains: tuple[str, ...] = ()


@dataclass
class Candidate:
    source: str
    url: str
    title: str
    summary: str = ""
    feed_time_raw: str = ""
    discovered_from: str = ""
    context: str = ""


@dataclass
class Article:
    # Per-instance preparation only. Excluded from dataclass serialization,
    # equality and constructors; deepcopy preserves it, replace recomputes.
    _source_kind_snapshot: ClassVar[tuple[str, str, tuple[str, ...], str] | None] = None
    source: str
    url: str
    title: str
    summary: str
    key_facts: list[str]
    category: str
    published_utc: datetime
    published_raw: str
    published_source: str
    confidence: str
    tokens: set[str]
    event_kind: str = "general_company"
    relevance_tier: str = "strong"
    relevance_reason: str = ""
    regions: set[str] = field(default_factory=set)
    projection_child_key: str = ""
    projection_parent_keys: frozenset[str] = field(default_factory=frozenset)
    evidence: ArticleEvidence | None = field(default=None, compare=False, repr=False)
    bound_claim: BoundClaim | None = None
    projection_source_title: str = ""
    projected_fact_spans: tuple[tuple[str, int, int], ...] | None = None


@dataclass
class Event:
    event_id: str
    category: str
    title: str
    summary: str
    key_facts: list[str]
    published_utc: datetime
    published_raw: str
    published_source: str
    confidence: str
    articles: list[Article]
    tokens: set[str]
    event_kind: str = "general_company"
    relevance_tier: str = "strong"
    relevance_reason: str = ""
    regions: set[str] = field(default_factory=set)
    merge_warnings: list[str] = field(default_factory=list)
    fact_plan: EventFactPlan | None = None



@dataclass(frozen=True)
class FetchSettings:
    timeout: float
    retries: int
    user_agent: str
    max_response_bytes: int


@dataclass(frozen=True)
class EvidenceUnit:
    unit_id: str
    kind: str
    text: str
    origin: str
    ordinal: int
    container_id: str = ""


@dataclass(frozen=True)
class PublicationEvidence:
    raw: str
    source: str
    allows_date_only: bool = False


@dataclass(frozen=True)
class EmbeddedReference:
    platform: str
    object_id: str
    url: str
    origin: str
    body_element_index: int
    html_tag: str


@dataclass(frozen=True)
class ArticleEvidence:
    article_id: str
    source: str
    url: str
    title: str
    raw_lead: str
    content_form: str
    units: tuple[EvidenceUnit, ...]
    publication_candidates: tuple[PublicationEvidence, ...] = ()
    published_utc: str | None = None
    published_raw: str = ""
    published_source: str = ""
    confidence: str = ""
    extraction_path: str = "detail"
    discovery_title: str = ""
    discovery_lead: str = ""
    embedded_references: tuple[EmbeddedReference, ...] = ()


@dataclass(frozen=True)
class BoundClaim:
    subject: str
    action: str
    object: str
    # target, qualifier kind, normalized value, source unit id, start, end.
    # Each target owns its value; language and month sets are never crossed.
    qualifiers: tuple[tuple[str, str, str, str, int, int], ...]
    article_id: str
    unit_ids: tuple[str, ...]
    # Each fact is an exact, source-local span: unit id, start, end.
    evidence_spans: tuple[tuple[str, int, int], ...]
    parent_form: str
    category: str = ""
    event_kind: str = ""


@dataclass(frozen=True)
class ReconciliationProfile:
    event_keys: frozenset[str]
    boundary_keys: frozenset[str]
    exact_facets: frozenset[str] = frozenset()
    separation_keys: frozenset[str] = frozenset()
    defer_reason: str = ""
    category_hint: str = ""
    observed_category: str = ""
    hard_boundary: str = ""
    identity: EventIdentity | None = None
    relevance_tier: str = "strong"
    trusted_direct_action: bool = False
    promotion_reason: str = ""
    bound_claim: BoundClaim | None = None
    event_kind_hint: str = ""
    ecosystem_reason: str = ""
    parent_source: ReconciliationProfile | None = None



@dataclass(frozen=True)
class PreparedFact:
    text: str
    key: str
    priority: int = 0
    roles: frozenset[str] = frozenset()
    # source, URL, evidence article id, unit id, local start, local end.
    origins: tuple[tuple[str, str, str, str, int, int], ...] = ()
    owned: bool = False
    reason: str = ""


@dataclass(frozen=True)
class SourceFactView:
    source: str
    url: str
    source_priority: int
    published_utc: datetime
    official: bool
    raw_fact_count: int
    compact_hardware_price: bool
    normal: tuple[PreparedFact, ...] = ()
    structured: tuple[PreparedFact, ...] = ()
    price: tuple[PreparedFact, ...] = ()
    responses: tuple[PreparedFact, ...] = ()
    owned: tuple[PreparedFact, ...] = ()
    display_title: str = ""
    summary_units: tuple[str, ...] = ()
    required_actions: tuple[PreparedFact, ...] = ()
    unprocessed: tuple[PreparedFact, ...] = ()


@dataclass(frozen=True)
class EventFactPlan:
    title: str
    summary: str
    facts: tuple[PreparedFact, ...]
    required: tuple[PreparedFact, ...] = ()
    unprocessed: tuple[PreparedFact, ...] = ()
