"""Deterministic pair matching for title-led Apple news event identities."""

from __future__ import annotations

from typing import Literal

from .event_identity import CROSS_PRODUCT_IDENTITY_FACETS, EventIdentity


MergeDecision = Literal["match", "conflict", "unknown"]

APP_STORE_TARGET_COMPONENTS = {"nudify-apps", "gambling-apps"}

PRICE_CONTEXT_FACETS = {
    "apple-price-external-reaction",
    "apple-price-production-plan-response",
    "apple-price-retailer-retroactive-adjustment",
    "apple-price-stock-market-reaction",
    "apple-price-supplier-cost-dispute",
    "apple-refurbished-store-price-context",
    "apple-retail-promotion-price-context",
}

HIGH_CONFIDENCE_COMPONENTS = {
    "app-catalog-metrics",
    "camera-system",
    "car-key",
    "customer-loyalty",
    "dual-battery",
    "hide-my-email",
    "market-cap",
    "memory-supply",
    "nudify-apps",
    "gambling-apps",
    "office-real-estate",
    "oled-display",
    "privacy-vulnerability",
    "price-upgrade-behavior",
    "recovery-mode",
    "server-chip",
    "spotlight-index-preparation",
    "vapor-chamber",
    "writing-tools",
}

HIGH_SIGNAL_NAMED_SUBJECT_ACTIONS = {
    "delay-roadmap",
    "feature-change",
    "legal",
    "pilot-testing",
    "project-cancellation",
    "content-release",
    "platform-trust",
    "regulation",
    "security",
    "supply-production",
    "transaction",
}

FIRST_PARTY_SERVICE_PRODUCTS = {
    "apple-arcade",
    "apple-books",
    "apple-music",
    "apple-one",
    "apple-sports",
    "apple-tv",
    "icloud",
}


def _one_edit_apart(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < 8 or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    index = offset = differences = 0
    while index < len(shorter) and index + offset < len(longer):
        if shorter[index] == longer[index + offset]:
            index += 1
            continue
        differences += 1
        if differences > 1:
            return False
        offset += 1
    return True


def _compatible_named_subjects(left: frozenset[str], right: frozenset[str]) -> set[tuple[str, str]]:
    return {
        (left_subject, right_subject)
        for left_subject in left
        for right_subject in right
        if _one_edit_apart(left_subject, right_subject)
    }

MEMORY_SUPPLY_CONTEXT_COMPONENTS = {
    "memory-order-allocation",
    "memory-policy-restriction",
    "memory-supplier-sourcing",
}


def _products_compatible(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left or not right:
        return True
    if left & right:
        return True
    iphone_family = {"iphone", "foldable-iphone"}
    ipad_family = {"ipad", "ipad-mini", "ipad-air", "ipad-pro"}
    return bool(left <= iphone_family and right <= iphone_family) or bool(
        left <= ipad_family and right <= ipad_family and ("ipad" in left or "ipad" in right)
    )


def _actions_compatible(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left or not right:
        return True
    if left & right:
        return True
    related = (
        {"legal", "security"},
        {"supply-production", "delay-roadmap"},
        {"retail-availability", "delay-roadmap"},
        {"market-report", "feature-change"},
    )
    return any(bool(left & group) and bool(right & group) for group in related)


def _legal_decision(left: EventIdentity, right: EventIdentity) -> MergeDecision | None:
    # A company name in a short lead is only background until the title or lead
    # also establishes an actual proceeding. Treating counterparties alone as
    # legal identity lets unrelated stories that mention OpenAI, DOJ, or Epic
    # collapse into one event.
    left_is_legal = bool("legal" in left.actions or left.case_topics)
    right_is_legal = bool("legal" in right.actions or right.case_topics)
    if not (left_is_legal and right_is_legal):
        return None
    if (
        left.counterparties
        and right.counterparties
        and not (left.counterparties & right.counterparties)
    ):
        return "conflict"
    if left.case_topics and right.case_topics and not (left.case_topics & right.case_topics):
        return "conflict"
    if (left.counterparties & right.counterparties) or (left.case_topics & right.case_topics):
        return "match"
    return "unknown"


def _price_decision(left: EventIdentity, right: EventIdentity) -> MergeDecision | None:
    if not ({"price-change"} <= left.actions and {"price-change"} <= right.actions):
        return None
    if "price-change" not in left.title_actions or "price-change" not in right.title_actions:
        return None
    left_context = left.facets & PRICE_CONTEXT_FACETS
    right_context = right.facets & PRICE_CONTEXT_FACETS
    if left_context != right_context and (left_context or right_context):
        return "conflict"
    left_forecast = "future-price-forecast" in left.components
    right_forecast = "future-price-forecast" in right.components
    if left_forecast != right_forecast:
        return "conflict"
    if left.products and right.products:
        if left.products & right.products:
            return "match"
        return "conflict"
    return "unknown"


def identity_pair_decision(left: EventIdentity, right: EventIdentity) -> MergeDecision:
    """Resolve only high-confidence identities; leave nuanced cases to legacy guards."""
    if left.scope == "third-party-context" or right.scope == "third-party-context":
        if left.scope != right.scope:
            return "conflict"

    shared_components = left.components & right.components
    if any(
        component.startswith(("os-wave:", "os-wave-platform:"))
        for component in shared_components
    ):
        return "match"

    legal_decision = _legal_decision(left, right)
    if legal_decision is not None:
        return legal_decision

    price_decision = _price_decision(left, right)
    if price_decision is not None:
        return price_decision

    if "app-store" in left.products and "app-store" in right.products:
        left_targets = left.components & APP_STORE_TARGET_COMPONENTS
        right_targets = right.components & APP_STORE_TARGET_COMPONENTS
        if left_targets and right_targets:
            return "match" if left_targets & right_targets else "conflict"

    if "memory-supply" in left.components and "memory-supply" in right.components:
        left_context = left.title_components & MEMORY_SUPPLY_CONTEXT_COMPONENTS
        right_context = right.title_components & MEMORY_SUPPLY_CONTEXT_COMPONENTS
        if left_context and right_context:
            return "match" if left_context & right_context else "conflict"

    shared_title_components = left.title_components & right.title_components
    shared_facets = left.facets & right.facets
    shared_named_subjects = left.named_subjects & right.named_subjects
    compatible_named_subjects = _compatible_named_subjects(left.named_subjects, right.named_subjects)

    if "roundup" in {left.content_form, right.content_form} and left.content_form != right.content_form:
        specific = right if left.content_form == "roundup" else left
        if (
            specific.title_components & HIGH_CONFIDENCE_COMPONENTS
            or specific.named_subjects
            or specific.facets
        ):
            return "conflict"

    if "price-upgrade-behavior" in shared_title_components:
        return "match"
    if (
        "dual-battery" in shared_components
        and "dual-battery" in (left.title_components | right.title_components)
        and _products_compatible(left.products, right.products)
    ):
        return "match"

    if shared_named_subjects or compatible_named_subjects:
        shared_actions = left.actions & right.actions & HIGH_SIGNAL_NAMED_SUBJECT_ACTIONS
        if shared_actions and _products_compatible(left.products, right.products):
            return "match"
    if (
        left.named_subjects
        and right.named_subjects
        and not shared_named_subjects
        and "pilot-testing" in left.actions
        and "pilot-testing" in right.actions
    ):
        return "conflict"

    shared_office_places = {
        component for component in shared_components if component.startswith("office-place:")
    }
    if (
        shared_office_places
        and "office-real-estate" in shared_components
        and "transaction" in left.actions
        and "transaction" in right.actions
    ):
        return "match"
    shared_first_party_services = left.products & right.products & FIRST_PARTY_SERVICE_PRODUCTS
    if (
        shared_first_party_services
        and left.facets
        and right.facets
        and not (left.facets & right.facets)
    ):
        return "conflict"
    if shared_first_party_services and left.actions & right.actions & {
        "content-release",
        "market-report",
        "platform-trust",
        "price-change",
        "retail-availability",
    }:
        return "match"
    concrete_components = shared_components & HIGH_CONFIDENCE_COMPONENTS
    if (
        concrete_components
        and (shared_title_components & concrete_components)
        and _products_compatible(left.products, right.products)
        and _actions_compatible(left.actions, right.actions)
    ):
        return "match"
    if "product-release-mix" in shared_components:
        return "match"
    if shared_facets & CROSS_PRODUCT_IDENTITY_FACETS:
        return "match"

    if (
        left.title_products
        and right.title_products
        and not _products_compatible(left.title_products, right.title_products)
        and left.title_actions
        and right.title_actions
        and not _actions_compatible(left.title_actions, right.title_actions)
        and not (left.actors & right.actors)
        and not (left.counterparties & right.counterparties)
    ):
        return "conflict"
    if (
        left.title_products
        and right.title_products
        and not _products_compatible(left.title_products, right.title_products)
        and "hands_on" in {left.content_form, right.content_form}
        and left.content_form != right.content_form
        and not shared_facets
    ):
        return "conflict"

    left_concrete = left.title_components & HIGH_CONFIDENCE_COMPONENTS
    right_concrete = right.title_components & HIGH_CONFIDENCE_COMPONENTS
    if left_concrete and right_concrete and not (left_concrete & right_concrete):
        if left.title_products & right.title_products or left.actions & right.actions:
            return "conflict"
    return "unknown"
