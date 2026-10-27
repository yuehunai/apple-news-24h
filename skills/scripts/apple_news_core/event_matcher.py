"""Deterministic pair matching for title-led Apple news event identities."""

from __future__ import annotations

import re
from typing import Literal, Sequence

from .models import BoundClaim, ReconciliationProfile

from .event_identity import CROSS_PRODUCT_IDENTITY_FACETS, UMBRELLA_FACETS, EventIdentity, EVIDENCE_BACKED_COMPONENTS


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
    "apple-data-integration",
    "apple-device-leasing-program",
    "app-catalog-metrics",
    "camera-system",
    "clipboard-paste-suggestion",
    "car-key",
    "customer-loyalty",
    "cross-platform-data-migration",
    "dual-battery",
    "exclusive-display-supplier",
    "financed-device-restriction",
    "facility-renovation",
    "hide-my-email",
    "largest-iphone-display",
    "ltpo-display",
    "market-cap",
    "macbook-model:air",
    "macbook-model:neo",
    "macbook-model:pro",
    "macbook-model:ultra",
    "memory-supply",
    "nudify-apps",
    "gambling-apps",
    "office-real-estate",
    "oled-display",
    "product-patent-disclosure",
    "price-upgrade-behavior",
    "production-hurdle",
    "product-release-delay",
    "recovery-mode",
    "recurring-transactions",
    "server-chip",
    "shopping-assistant",
    "spotlight-index-preparation",
    "supplier-input-cost",
    "vapor-chamber",
    "water-resistance",
    "writing-tools",
}

HIGH_SIGNAL_NAMED_SUBJECT_ACTIONS = {
    "delay-roadmap",
    "feature-change",
    "legal",
    "official-communication",
    "pilot-testing",
    "platform-integration",
    "project-cancellation",
    "content-release",
    "platform-trust",
    "price-change",
    "regulation",
    "security",
    "supply-production",
    "transaction",
}

LOW_SIGNAL_NAMED_SUBJECTS = {
    "apple-ceo",
    "ceo",
}


def _high_confidence_components(components: frozenset[str]) -> set[str]:
    return {
        component
        for component in components
        if component in HIGH_CONFIDENCE_COMPONENTS
        or component.startswith("display-size:")
        or component.startswith("analyst-institution:")
        or component.startswith("os-component:")
    }

FIRST_PARTY_SERVICE_PRODUCTS = {
    "apple-arcade",
    "apple-books",
    "apple-fitness",
    "apple-wallet",
    "apple-music",
    "apple-one",
    "apple-sports",
    "apple-tv",
    "icloud",
    "shazam",
    "applecare",
}


_SUBJECT_NUMBERS = re.compile(r"\d+")


def _one_edit_apart(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < 8 or abs(len(left) - len(right)) > 1:
        return False
    # Digits identify model generations, not spelling variations.
    if _SUBJECT_NUMBERS.findall(left) != _SUBJECT_NUMBERS.findall(right):
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
        {"feature-change", "delay-roadmap"},
        {"feature-change", "retail-availability"},
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
    left_is_legal = "legal" in left.actions
    right_is_legal = "legal" in right.actions
    if left_is_legal != right_is_legal and "product-patent-disclosure" in (
        left.components | right.components
    ):
        return "conflict"
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
    # Retire the broad trade-secret grant here and in exact facets together.
    # Other legacy legal families retain their behavior until case relations migrate.
    if ((left.counterparties & right.counterparties)
            or ((left.case_topics & right.case_topics) - {"trade-secret"})):
        return "match"
    return "unknown"


def _price_object_conflict(left: EventIdentity, right: EventIdentity) -> bool:
    return bool(
        "price-change" in left.title_actions & right.title_actions
        and (("trade-in-valuation" in left.title_components)
             != ("trade-in-valuation" in right.title_components))
    )


def _price_decision(left: EventIdentity, right: EventIdentity) -> MergeDecision | None:
    if _price_object_conflict(left, right):
        return "conflict"
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
    left_supplier_cost = "supplier-input-cost" in left.components
    right_supplier_cost = "supplier-input-cost" in right.components
    if left_supplier_cost != right_supplier_cost:
        return "conflict"
    if left_supplier_cost and right_supplier_cost:
        left_title_supplier_cost = "supplier-input-cost" in left.title_components
        right_title_supplier_cost = "supplier-input-cost" in right.title_components
        if left_title_supplier_cost != right_title_supplier_cost:
            return "conflict"
        if (left.named_subjects & right.named_subjects) or (left.actors & right.actors):
            return "match"
    if left.products and right.products:
        if left.products & right.products:
            return "match"
        return "conflict"
    return "unknown"


def identity_pair_decision(left: EventIdentity | BoundClaim, right: EventIdentity | BoundClaim) -> MergeDecision:
    """Resolve only high-confidence identities; leave nuanced cases to legacy guards."""
    if isinstance(left, BoundClaim) or isinstance(right, BoundClaim):
        if not isinstance(left, BoundClaim) or not isinstance(right, BoundClaim):
            return "unknown"
        if not all((left.subject, left.action, left.object, right.subject, right.action, right.object)):
            return "unknown"
        if (left.subject, left.action, left.object) != (right.subject, right.action, right.object):
            return "conflict"
        if left.polarity and right.polarity and left.polarity != right.polarity:
            return "conflict"
        if left.report_role and right.report_role and left.report_role != right.report_role:
            return "conflict"
        if left.action in {'resale-quote-report', 'delivery-wait-report'}:
            if left.article_id and left.article_id == right.article_id:
                return 'match'
            records = [tuple(dict.fromkeys(q[2] for q in claim.qualifiers if q[1] == 'observation-sentence'))
                       for claim in (left, right)]
            return 'match' if records[0] and records[0] == records[1] else 'unknown'
        if left.action == 'resale-order-report':
            records = [{kind: {q[2] for q in c.qualifiers if q[1] == kind}
                        for kind in {q[1] for q in c.qualifiers}} for c in (left, right)]
            if any(len(values) != 1 for record in records for values in record.values()):
                return 'unknown'
            shared = records[0].keys() & records[1].keys()
            if any(records[0][key] != records[1][key] for key in shared):
                return 'conflict'
            return 'match' if 'report-party' in shared and shared & {'order-total', 'order-deposit'} else 'unknown'
        if left.action == 'leadership-report':
            # The same speaker, publisher and topic do not identify an
            # interview instance. Keep qualification independent of pairing.
            return 'unknown'
        if left.action == 'media-invitation':
            dates = [{kind: {q[2] for q in claim.qualifiers if q[1] == kind}
                      for kind in ('event-year', 'event-month', 'event-day')} for claim in (left, right)]
            if any(not all(len(d[k]) == 1 for k in ('event-month', 'event-day'))
                   or len(d['event-year']) > 1 for d in dates):
                return 'unknown'
            if any(dates[0][k] and dates[1][k] and dates[0][k] != dates[1][k] for k in dates[0]):
                return 'conflict'
        if left.action == 'app-publisher-chart-report':
            charts = [{q[2] for q in claim.qualifiers if q[1] == 'chart-kind'} for claim in (left, right)]
            if not charts[0].intersection(charts[1]):
                return "unknown"
        # A source-local object/action binding is positive evidence. Qualifiers
        # that both sources specify must not contradict it.
        left_values = {(q[0], q[1]): q[2] for q in left.qualifiers if q[1] in {"rollout-time", "rollout-year", "price-amount", "quota-from", "quota-to", "code-version", "appointment-holder", "observation-year", "observation-month", "observation-day", "consultation-year", "consultation-month", "consultation-day", "incident-year", "incident-month", "incident-day", "test-duration"} and q[2] != "unspecified"}
        right_values = {(q[0], q[1]): q[2] for q in right.qualifiers if q[1] in {"rollout-time", "rollout-year", "price-amount", "quota-from", "quota-to", "code-version", "appointment-holder", "observation-year", "observation-month", "observation-day", "consultation-year", "consultation-month", "consultation-day", "incident-year", "incident-month", "incident-day", "test-duration"} and q[2] != "unspecified"}
        if any(left_values[key] != right_values[key] for key in left_values.keys() & right_values.keys()):
            return "conflict"
        if left.action == 'local-model-measurement':
            contexts = [{q[:3] for q in claim.qualifiers
                         if q[1] in {'measurement-context', 'observation-source'}}
                        for claim in (left, right)]
            if not contexts[0] or contexts[0] != contexts[1]:
                return 'unknown'
        if left.action == 'market-forecast-report':
            providers = [{q[2] for q in claim.qualifiers if q[1] == 'forecast-provider'} for claim in (left,right)]
            if providers[0] and providers[1] and providers[0] != providers[1]:
                return 'conflict'
            records = [{q[2] for q in claim.qualifiers if q[1] == 'forecast-record'} for claim in (left, right)]
            if not records[0].intersection(records[1]):
                return 'unknown'
        if left.action == 'retail-queue-observation':
            days = [{q[2] for q in claim.qualifiers if q[1] == 'queue-launch-day'} for claim in (left, right)]
            if days[0] and days[1] and not days[0].intersection(days[1]):
                return 'conflict'
            for kind in ('queue-count', 'queue-position-offer-cny', 'queue-overnight', 'queue-location'):
                values = [{q[2] for q in claim.qualifiers if q[1] == kind} for claim in (left, right)]
                if not values[0].intersection(values[1]):
                    return 'unknown'
        if left.action in {'cpu-benchmark-report', 'device-test-report', 'local-model-measurement', 'component-output-observation'}:
            dates = [{q[1:3] for q in claim.qualifiers if q[1].startswith('observation-')} for claim in (left, right)]
            records = [{q[2] for q in claim.qualifiers if q[1] == 'measurement-record'} for claim in (left, right)]
            if not (dates[0] and dates[0] == dates[1]) and not records[0].intersection(records[1]):
                return "unknown"
        return "match"
    shared_components = left.components & right.components
    left_primary_intents = {
        component for component in left.title_components if component.startswith("primary-intent:")
    }
    right_primary_intents = {
        component for component in right.title_components if component.startswith("primary-intent:")
    }
    if left_primary_intents and right_primary_intents and not (
        left_primary_intents & right_primary_intents
    ):
        return "conflict"
    left_analyst_target = "analyst-target-action" in left.title_components
    right_analyst_target = "analyst-target-action" in right.title_components
    if left_analyst_target != right_analyst_target:
        return "conflict"
    left_analyst_institutions = {
        component
        for component in left.title_components
        if component.startswith("analyst-institution:")
    }
    right_analyst_institutions = {
        component
        for component in right.title_components
        if component.startswith("analyst-institution:")
    }
    if left_analyst_institutions and right_analyst_institutions:
        if not (left_analyst_institutions & right_analyst_institutions):
            return "conflict"
        if "apple-analyst-rating-target" in left.facets & right.facets:
            return "match"
    left_iphone_models = {
        component
        for component in left.title_components
        if component.startswith(("iphone-model:", "iphone-family:", "iphone-line:"))
    }
    right_iphone_models = {
        component
        for component in right.title_components
        if component.startswith(("iphone-model:", "iphone-family:", "iphone-line:"))
    }
    if left_iphone_models and right_iphone_models:
        compatible_models = bool(left_iphone_models & right_iphone_models)
        if not compatible_models:
            left_air = any(
                component == "iphone-line:air" or component.startswith("iphone-model:air-")
                for component in left_iphone_models
            )
            right_air = any(
                component == "iphone-line:air" or component.startswith("iphone-model:air-")
                for component in right_iphone_models
            )
            compatible_models = left_air and right_air
        if not compatible_models:
            return "conflict"
    shared_specific_iphone_models = {
        component
        for component in left_iphone_models & right_iphone_models
        if component.startswith("iphone-model:")
    }
    shared_report_attributions = {
        component
        for component in left.components & right.components
        if component.startswith("report-attribution:")
    }
    shared_report_actions = left.actions & right.actions & {
        "delay-roadmap",
        "feature-change",
        "market-report",
        "price-change",
        "retail-availability",
        "supply-production",
    }
    if (
        shared_specific_iphone_models
        and shared_report_attributions
        and shared_report_actions
        and _products_compatible(left.products, right.products)
    ):
        return "match"
    left_title_services = left.title_products & FIRST_PARTY_SERVICE_PRODUCTS
    right_title_services = right.title_products & FIRST_PARTY_SERVICE_PRODUCTS
    if (
        ("applecare" in left_title_services) != ("applecare" in right_title_services)
        and left_title_services
        and right_title_services
    ):
        return "conflict"
    direct_first_party_products = FIRST_PARTY_SERVICE_PRODUCTS | {
        "airpods",
        "beats",
        "apple-glasses",
        "apple-home-hub",
        "apple-watch",
        "homepod",
        "ipad",
        "ipad-air",
        "ipad-base",
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
    left_direct_products = left.title_products & direct_first_party_products
    right_direct_products = right.title_products & direct_first_party_products
    shared_named_subjects = (left.named_subjects & right.named_subjects) - LOW_SIGNAL_NAMED_SUBJECTS
    shared_content_release = "content-release" in left.actions & right.actions
    named_service_content_match = bool(
        shared_named_subjects
        and shared_content_release
        and ((left_title_services | right_title_services) & FIRST_PARTY_SERVICE_PRODUCTS)
    )
    if (
        left_direct_products
        and right_direct_products
        and not _products_compatible(left_direct_products, right_direct_products)
        and not (
            left_direct_products <= FIRST_PARTY_SERVICE_PRODUCTS
            and right_direct_products <= FIRST_PARTY_SERVICE_PRODUCTS
        )
        and not named_service_content_match
        and not (left.facets & right.facets & CROSS_PRODUCT_IDENTITY_FACETS)
    ):
        return "conflict"
    if (
        "cross-platform-data-migration" in shared_components
        and _products_compatible(left.products, right.products)
    ):
        return "match"
    if left.scope == "third-party-context" or right.scope == "third-party-context":
        if left.scope != right.scope:
            return "conflict"

    left_version_waves = {
        component for component in left.components if component.startswith("os-wave:")
    }
    right_version_waves = {
        component for component in right.components if component.startswith("os-wave:")
    }
    left_platform_waves = {
        component
        for component in left.components
        if component.startswith("os-wave-platform:")
    }
    right_platform_waves = {
        component
        for component in right.components
        if component.startswith("os-wave-platform:")
    }
    if left_version_waves and right_version_waves:
        shared_version_waves = left_version_waves & right_version_waves
        if not shared_version_waves:
            return "conflict"
        # A numbered beta/public-beta batch is one coordinated Apple release
        # action across platforms. Final releases need a concrete platform
        # anchor because each OS ships as an independently reportable event.
        if any(not component.endswith(":final") for component in shared_version_waves):
            return "match"
        if left_platform_waves and right_platform_waves:
            left_platforms = {
                component.split(":", 2)[1] for component in left_platform_waves
            }
            right_platforms = {
                component.split(":", 2)[1] for component in right_platform_waves
            }
            mobile_platforms = {"ios", "ipados"}
            if not (
                left_platforms & right_platforms
                or (left_platforms <= mobile_platforms and right_platforms <= mobile_platforms)
            ):
                return "conflict"
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

    if (
        "water-resistance" in shared_components
        and _products_compatible(left.products, right.products)
        and _actions_compatible(left.actions, right.actions)
    ):
        return "match"

    if (
        "exclusive-display-supplier" in shared_components
        and _products_compatible(left.products, right.products)
    ):
        return "match"

    if "memory-supply" in left.components and "memory-supply" in right.components:
        left_context = left.title_components & MEMORY_SUPPLY_CONTEXT_COMPONENTS
        right_context = right.title_components & MEMORY_SUPPLY_CONTEXT_COMPONENTS
        if left_context and right_context:
            return "match" if left_context & right_context else "conflict"

    financing_components = {"apple-device-leasing-program", "financed-device-restriction"}
    left_financing = left.components & financing_components
    right_financing = right.components & financing_components
    if left_financing and right_financing and not (left_financing & right_financing):
        return "conflict"

    left_chip_generations = {
        component
        for component in left.title_components
        if component.startswith("apple-silicon-generation:")
    }
    right_chip_generations = {
        component
        for component in right.title_components
        if component.startswith("apple-silicon-generation:")
    }
    if bool(left_chip_generations) != bool(right_chip_generations):
        chip_identity = left if left_chip_generations else right
        companion_identity = right if left_chip_generations else left
        companion_primary_intents = {
            component
            for component in companion_identity.title_components
            if component.startswith("primary-intent:")
        }
        if (
            not chip_identity.title_products
            and (
                companion_identity.title_products
                or companion_primary_intents
            )
        ):
            # A chip generation named only in one headline owns that event.
            # Device, price, or other title-led actions may mention the chip in
            # their body, but that background cannot turn them into chip news.
            return "conflict"
    if (
        left_chip_generations
        and right_chip_generations
        and not (left_chip_generations & right_chip_generations)
    ):
        return "conflict"
    shared_chip_generations = left_chip_generations & right_chip_generations
    shared_chip_variants = {
        subject
        for subject in left.title_named_subjects & right.title_named_subjects
        if any(
            subject.endswith(suffix)
            for suffix in ("-pro", "-max", "-ultra")
        )
        and subject[:1] in {"m", "a"}
    }
    if (
        shared_chip_generations
        and shared_chip_variants
        and _products_compatible(left.products, right.products)
    ):
        return "match"

    left_market_performance = "hardware-market-performance" in left.title_components
    right_market_performance = "hardware-market-performance" in right.title_components
    left_product_roadmap = "hardware-product-roadmap" in left.title_components
    right_product_roadmap = "hardware-product-roadmap" in right.title_components
    if (
        left_market_performance
        and right_product_roadmap
        and not left_product_roadmap
        and not right_market_performance
    ) or (
        right_market_performance
        and left_product_roadmap
        and not right_product_roadmap
        and not left_market_performance
    ):
        return "conflict"

    left_concrete_components = _high_confidence_components(left.components)
    right_concrete_components = _high_confidence_components(right.components)
    shared_home_hub_roadmap = bool(
        "apple-home-hub" in left.title_products & right.title_products
        and "hardware-product-roadmap" in (left.components | right.components)
        and left.scope == "apple-direct"
        and right.scope == "apple-direct"
        and _actions_compatible(left.actions, right.actions)
        and bool(
            (left.actions | right.actions)
            & {"delay-roadmap", "retail-availability"}
        )
    )
    left_title_data_integration = "apple-data-integration" in left.title_components
    right_title_data_integration = "apple-data-integration" in right.title_components
    if left_title_data_integration != right_title_data_integration:
        return "conflict"
    data_integration_intents = {
        "apple-data-integration-rollout",
        "apple-data-integration-commentary",
    }
    left_data_intents = left.title_components & data_integration_intents
    right_data_intents = right.title_components & data_integration_intents
    if left_data_intents and right_data_intents and not (left_data_intents & right_data_intents):
        return "conflict"
    if (
        left_concrete_components
        and right_concrete_components
        and not (left_concrete_components & right_concrete_components)
        and bool(left.products & right.products)
        and not ((left.facets & right.facets) - UMBRELLA_FACETS)
        and not shared_home_hub_roadmap
    ):
        return "conflict"
    shared_title_components = left.title_components & right.title_components
    shared_facets = left.facets & right.facets
    shared_named_subjects = (left.named_subjects & right.named_subjects) - LOW_SIGNAL_NAMED_SUBJECTS
    compatible_named_subjects = {
        pair
        for pair in _compatible_named_subjects(left.named_subjects, right.named_subjects)
        if not ({pair[0], pair[1]} & LOW_SIGNAL_NAMED_SUBJECTS)
    }
    shared_title_named_subjects = left.title_named_subjects & right.title_named_subjects
    compatible_title_named_subjects = _compatible_named_subjects(
        left.title_named_subjects,
        right.title_named_subjects,
    )
    left_product_generations = {
        component
        for component in left.title_components
        if component.startswith("product-generation:")
    }
    right_product_generations = {
        component
        for component in right.title_components
        if component.startswith("product-generation:")
    }
    if (
        left_product_generations
        and right_product_generations
        and not (left_product_generations & right_product_generations)
    ):
        return "conflict"
    left_os_components = {
        component for component in left.title_components if component.startswith("os-component:")
    }
    right_os_components = {
        component for component in right.title_components if component.startswith("os-component:")
    }
    if left_os_components and right_os_components:
        if not (left_os_components & right_os_components):
            return "conflict"
        if _products_compatible(left.products, right.products):
            return "match"
    left_content_lifecycle = {
        component for component in left.components if component.startswith("content-lifecycle:")
    }
    right_content_lifecycle = {
        component for component in right.components if component.startswith("content-lifecycle:")
    }
    if left_content_lifecycle and right_content_lifecycle:
        if (
            not (left_content_lifecycle & right_content_lifecycle)
            and "content-lifecycle:ending" in (left_content_lifecycle | right_content_lifecycle)
        ):
            return "conflict"
        shared_content_markers = {
            component
            for component in shared_components
            if component.startswith(("content-season:", "content-year:"))
        }
        if (
            shared_content_markers
            and "apple-tv" in left.products & right.products
        ):
            return "match"
    left_foldable = "foldable-iphone" in left.title_products
    right_foldable = "foldable-iphone" in right.title_products
    if left_foldable != right_foldable and (
        left_product_generations or right_product_generations
    ):
        return "conflict"
    hardware_products = {
        "airpods",
        "apple-watch",
        "apple-home-hub",
        "foldable-iphone",
        "homepod",
        "imac",
        "ipad",
        "ipad-air",
        "ipad-base",
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
    if (
        left.title_products & hardware_products
        and right.title_products & hardware_products
        and not _products_compatible(
            frozenset(left.title_products & hardware_products),
            frozenset(right.title_products & hardware_products),
        )
        and not (shared_facets & CROSS_PRODUCT_IDENTITY_FACETS)
    ):
        return "conflict"
    left_macbook_models = {
        component
        for component in left.title_components
        if component.startswith("macbook-model:")
    }
    right_macbook_models = {
        component
        for component in right.title_components
        if component.startswith("macbook-model:")
    }
    if (
        left_macbook_models
        and right_macbook_models
        and not (left_macbook_models & right_macbook_models)
    ):
        return "conflict"
    if (
        left_product_generations & right_product_generations
        and "production-ramp" in shared_components
        and "production-ramp" in (left.title_components | right.title_components)
        and "supply-production" in left.actions & right.actions
        and _products_compatible(left.title_products, right.title_products)
    ):
        return "match"
    if (
        "production-hurdle" in shared_components
        and "production-hurdle" in (left.title_components | right.title_components)
        and _products_compatible(left.products, right.products)
        and _actions_compatible(left.actions, right.actions)
    ):
        return "match"
    if (
        "apple-data-integration" in shared_components
        and "platform-integration" in left.actions & right.actions
    ):
        return "match"

    if "roundup" in {left.content_form, right.content_form} and left.content_form != right.content_form:
        specific = right if left.content_form == "roundup" else left
        if (
            _high_confidence_components(specific.title_components)
            or specific.named_subjects
            or specific.facets
        ):
            return "conflict"

    if "price-upgrade-behavior" in shared_title_components:
        return "match"
    if "apple-device-leasing-program" in shared_title_components:
        return "match"
    if (
        "financed-device-restriction" in shared_title_components
        and (
            _products_compatible(left.products, right.products)
            or (
                bool(left.products & {"ios", "iphone"})
                and bool(right.products & {"ios", "iphone"})
                and left.products <= {"ios", "iphone"}
                and right.products <= {"ios", "iphone"}
            )
        )
    ):
        return "match"
    if (
        "dual-battery" in shared_components
        and "dual-battery" in (left.title_components | right.title_components)
        and _products_compatible(left.products, right.products)
    ):
        return "match"
    if (
        "product-patent-disclosure" in shared_components
        and "product-patent-disclosure" in (left.title_components | right.title_components)
        and _products_compatible(left.products, right.products)
    ):
        return "match"

    # The identity record stores names and actions as independent sets. A
    # common name is sufficient here only when both headlines establish it
    # as their subject. Body evidence remains available to source profiles,
    # whose concrete subject/predicate assertions can authorize a match.
    if shared_title_named_subjects or compatible_title_named_subjects:
        left_software = {c for c in left.components if c.startswith("device-software-release:")}
        right_software = {c for c in right.components if c.startswith("device-software-release:")}
        if (left_software or right_software) and not left_software & right_software:
            # A shared device name and independent action bags cannot equate
            # software availability with a forecast of its physical successor.
            return "unknown"
        shared_actions = left.title_actions & right.title_actions & HIGH_SIGNAL_NAMED_SUBJECT_ACTIONS
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
    if "apple-tv" in shared_first_party_services and "apple-tv-content" in (
        left.facets | right.facets
    ):
        left_titles = left.title_named_subjects
        right_titles = right.title_named_subjects
        if left_titles and right_titles:
            if not (
                (left_titles & right_titles)
                or _compatible_named_subjects(left_titles, right_titles)
            ):
                return "conflict"
        elif left_titles or right_titles:
            return "unknown"
    if (
        shared_first_party_services
        and left.facets
        and right.facets
        and not (left.facets & right.facets)
    ):
        return "conflict"
    apple_tv_content_with_title_identity = bool(
        "apple-tv" in shared_first_party_services
        and "apple-tv-content" in (left.facets | right.facets)
        and (left.title_named_subjects or right.title_named_subjects)
    )
    if (
        shared_first_party_services & left.title_products & right.title_products
        and not apple_tv_content_with_title_identity
        and left.title_actions & right.title_actions & {
        "content-release",
        "market-report",
        "platform-trust",
        "price-change",
        "retail-availability",
        }
    ):
        return "match"
    concrete_components = _high_confidence_components(shared_components)
    if "iphone" in (left.products | right.products):
        # Camera is a product part, not an action. Source-local adoption,
        # preview and imaging-feature claims supply their own pair authority.
        concrete_components.discard("camera-system")
    if (
        concrete_components
        and ((left.title_components & right.title_components) & concrete_components)
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

    left_concrete = _high_confidence_components(left.title_components)
    right_concrete = _high_confidence_components(right.title_components)
    if left_concrete and right_concrete and not (left_concrete & right_concrete):
        if left.title_products & right.title_products or left.actions & right.actions:
            return "conflict"
    return "unknown"


STRUCTURED_EVIDENCE_KEY_PREFIXES = (
    "structured-panel-report-measure:",
    "structured-canonical-title:",
    "structured-attributed-measure:",
    "structured-component-measure:",
    "structured-component-period:",
    "structured-entity-component:",
    "structured-legal-settlement:",
    "structured-claim-status:",
    "structured-market-result:",
    "structured-market-forecast:",
)


_SOFTWARE_FIRST_PARTY_PRODUCTS = {
    "apple-smart-home-os",
    "app-store",
    "apple-arcade",
    "apple-books",
    "apple-card",
    "apple-fitness",
    "apple-intelligence",
    "apple-maps",
    "apple-music",
    "apple-one",
    "apple-pay",
    "apple-sports",
    "apple-store-app",
    "apple-tv",
    "apple-wallet",
    "carplay",
    "homekit",
    "icloud",
    "ios",
    "ipados",
    "macos",
    "safari",
    "shazam",
    "siri",
    "tvos",
    "visionos",
    "watchos",
    "xcode",
}


_ACTION_EQUIVALENCE = {
    "availability-expansion": "availability-expansion",
    "catalog-expansion": "availability-expansion",
    "commercial-launch": "availability",
    "content-release": "content-release",
    "feature-change": "product-change",
    "official-communication": "official-communication",
    "price-change": "price-change",
    "product-disclosure": "disclosure",
    "product-launch": "availability",
    "product-refresh": "product-change",
    "retail-availability": "availability",
}


def _structured_title_action_classes(identity: EventIdentity) -> set[str]:
    raw_actions = set(identity.title_actions)
    if (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and not raw_actions
    ):
        raw_actions = set(identity.actions)
    classes = {
        _ACTION_EQUIVALENCE.get(action, action)
        for action in raw_actions
    }
    if (
        "product-launch" in identity.title_actions
        and "feature-change" not in identity.title_actions
    ):
        classes.discard("product-change")
    return classes


def _primary_title_subjects(identity: EventIdentity) -> set[str]:
    """Return the title entity that owns the concrete action.

    A named first-party product outranks chips, features, and other supporting
    components in the same headline. When no product is named, a concrete
    title component can own the action itself. This distinction prevents a
    legacy recall seed from treating a product launch and an accessory update
    as one event merely because their bodies share launch-day context.
    """
    if identity.title_products:
        subjects = set(identity.title_products)
        platform_context = {
            "ios",
            "ipados",
            "macos",
            "watchos",
            "tvos",
            "visionos",
        }
        specific_products = subjects - platform_context
        first_party_services = specific_products & _SOFTWARE_FIRST_PARTY_PRODUCTS
        if first_party_services:
            subjects = first_party_services
        if "security" in identity.actions:
            platform_aliases = {
                "iphone": "ios",
                "ipad": "ipados",
                "apple-watch": "watchos",
                "apple-tv": "tvos",
                "vision-pro": "visionos",
                "mac": "macos",
                "macbook": "macos",
                "imac": "macos",
                "mac-mini": "macos",
                "mac-studio": "macos",
                "mac-pro": "macos",
            }
            subjects |= {
                platform_aliases[subject]
                for subject in tuple(subjects)
                if subject in platform_aliases
            }
        return subjects
    return {
        component
        for component in identity.title_components
        if component.startswith("apple-silicon-generation:")
        or component in EVIDENCE_BACKED_COMPONENTS
        or component
        in {
            "genlock",
            "keyboard-key-labels",
            "maps-advertising",
            "private-cloud-compute-server",
        }
    }


def _direct_title_subject_conflict(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    """Reject a recall seed that joins different first-party action owners."""
    left_identity = left.identity
    right_identity = right.identity
    if left_identity is None or right_identity is None:
        return False
    if (
        left_identity.scope != "apple-direct"
        or right_identity.scope != "apple-direct"
        or left_identity.content_form != "news"
        or right_identity.content_form != "news"
    ):
        return False
    if left.exact_facets & right.exact_facets:
        return False
    pair_assertions = {
        key
        for key in left.event_keys | right.event_keys
        if key.startswith("structured-assertion:")
    }
    if (
        identity_pair_decision(left_identity, right_identity) == "match"
        and not pair_assertions
    ):
        return False
    if (
        left_identity.title_products & right_identity.title_products
        and left_identity.title_components & right_identity.title_components
    ):
        return False
    left_release_stages = {
        key.rsplit(":", 1)[-1]
        for key in left.event_keys
        if key.startswith(
            ("apple-os-release-wave:", "apple-os-platform-release-wave:")
        )
    }
    right_release_stages = {
        key.rsplit(":", 1)[-1]
        for key in right.event_keys
        if key.startswith(
            ("apple-os-release-wave:", "apple-os-platform-release-wave:")
        )
    }
    release_platform_products = {
        "ios",
        "iphone",
        "ipados",
        "ipad",
        "macos",
        "mac",
        "watchos",
        "apple-watch",
        "tvos",
        "apple-tv",
        "visionos",
        "vision-pro",
    }
    if (
        left_release_stages
        and left_release_stages == right_release_stages
        and bool(left_identity.title_products)
        and bool(right_identity.title_products)
        and left_identity.title_products <= release_platform_products
        and right_identity.title_products <= release_platform_products
        and "predicate:os-release-announcement" in left.separation_keys
        and "predicate:os-release-announcement" in right.separation_keys
    ):
        return False
    left_subjects = _primary_title_subjects(left_identity)
    right_subjects = _primary_title_subjects(right_identity)
    if not left_subjects or not right_subjects or not left_subjects.isdisjoint(right_subjects):
        return False
    shared_keys = left.event_keys & right.event_keys
    platform_subjects = {
        "ios",
        "iphone",
        "ipados",
        "ipad",
        "macos",
        "mac",
        "macbook",
        "imac",
        "mac-mini",
        "mac-studio",
        "mac-pro",
        "watchos",
        "apple-watch",
        "tvos",
        "apple-tv",
        "visionos",
        "vision-pro",
    }
    for key in shared_keys:
        if key.startswith(("apple-os-release-wave:", "apple-os-platform-release-wave:")):
            release_predicate = "predicate:os-release-announcement"
            left_assertions = {
                candidate
                for candidate in left.event_keys
                if candidate.startswith("structured-assertion:")
            }
            right_assertions = {
                candidate
                for candidate in right.event_keys
                if candidate.startswith("structured-assertion:")
            }
            independent_actions = {
                "claim-denial",
                "delay-roadmap",
                "legal",
                "price-change",
                "project-cancellation",
                "transaction",
            }
            if (
                release_predicate in left.separation_keys
                and release_predicate in right.separation_keys
                and left_assertions == right_assertions
                and not (left_identity.title_actions & independent_actions)
                and not (right_identity.title_actions & independent_actions)
            ):
                return False
            if left_subjects | right_subjects <= platform_subjects:
                return False
            continue
        if key.startswith(("canonical-apple-action:", "primary-claim:", "structured-assertion:")):
            return False
    return True


def _direct_title_action_conflict(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    """Keep explicit denials and distinct product operations separate.

    Action vocabularies vary heavily across sources and languages, so disjoint
    action labels alone are never a conflict. An explicit denial differs from
    affirmation. Otherwise, one title must assert a changed object while the other reports only
    the product lifecycle, and no precise identity key proves they are the same
    event.
    """
    left_identity = left.identity
    right_identity = right.identity
    if left_identity is None or right_identity is None:
        return False
    if (
        left_identity.scope != "apple-direct"
        or right_identity.scope != "apple-direct"
        or left_identity.content_form != "news"
        or right_identity.content_form != "news"
    ):
        return False
    if (("claim-polarity:explicit-denial" in left_identity.title_components)
            != ("claim-polarity:explicit-denial" in right_identity.title_components)
            and _primary_title_subjects(left_identity) & _primary_title_subjects(right_identity)):
        return True
    if left.exact_facets & right.exact_facets:
        return False
    if identity_pair_decision(left_identity, right_identity) == "match":
        return False
    left_subjects = _primary_title_subjects(left_identity)
    right_subjects = _primary_title_subjects(right_identity)
    if not left_subjects or not right_subjects or not (left_subjects & right_subjects):
        return False
    left_actions = _structured_title_action_classes(left_identity)
    right_actions = _structured_title_action_classes(right_identity)
    if not left_actions or not right_actions:
        return False
    shared_keys = left.event_keys & right.event_keys
    if any(
        key.startswith(
            (
                "canonical-apple-action:",
                "structured-assertion:",
                "structured-title-product-update:",
            )
        )
        for key in shared_keys
    ):
        return False
    if any(
        key.startswith(
            (
                "apple-firmware:",
                "apple-os-release-wave:",
                "canonical-apple-action:",
                "primary-claim:",
                "structured-assertion:",
                "structured-title-product-update:",
                "structured-title-product-release:",
            )
        )
        for key in shared_keys
    ):
        return False
    if any(
        key.startswith("product-period:")
        for key in left.separation_keys & right.separation_keys
    ):
        return False

    def is_concrete_change(profile: ReconciliationProfile, actions: set[str]) -> bool:
        return "product-change" in actions and any(
            key.startswith("changed-object:")
            for key in profile.separation_keys
        )

    def is_pure_lifecycle(actions: set[str]) -> bool:
        return bool(actions) and actions <= {"availability", "availability-expansion"}

    return bool(
        (is_concrete_change(left, left_actions) and is_pure_lifecycle(right_actions))
        or (is_concrete_change(right, right_actions) and is_pure_lifecycle(left_actions))
    )


def _disclosed_build_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    left_builds = {key for key in left.separation_keys if key.startswith("code-build:")}
    right_builds = {key for key in right.separation_keys if key.startswith("code-build:")}
    return bool(left_builds and right_builds and left_builds.isdisjoint(right_builds))


def _source_object_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    code_discovery = "primary-claim-predicate:feature-code-discovery"
    for discovery, other in ((left, right), (right, left)):
        if (code_discovery in discovery.separation_keys
                and "predicate:os-release-announcement" in other.separation_keys):
            return True
    disclosure = "primary-claim-predicate:unreleased-device-disclosure"
    if disclosure in left.separation_keys and disclosure in right.separation_keys:
        left_models = {k for k in left.separation_keys if k.startswith("product-model:")}
        right_models = {k for k in right.separation_keys if k.startswith("product-model:")}
        if left_models and right_models and left_models.isdisjoint(right_models):
            return True
    catalog = "primary-claim-predicate:document-catalog-report"
    if (catalog in left.separation_keys) != (catalog in right.separation_keys):
        # Publishing technical drawings is not a firmware/device update, even
        # if those devices appear in the document's inventory.
        return True
    return False


def _profiles_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    if _source_object_conflict(left, right):
        return True
    if _disclosed_build_conflict(left, right):
        return True
    if any(
        key.startswith("primary-claim:")
        for key in left.event_keys & right.event_keys
    ):
        # Exact primary claims encode both canonical subject and concrete
        # action. They are stronger identity evidence than incidental product
        # names or background actors elsewhere in either page.
        return False
    if _direct_title_subject_conflict(left, right):
        return True
    if _direct_title_action_conflict(left, right):
        return True
    if _weak_editorial_profile(left) != _weak_editorial_profile(right):
        return True
    if left.identity is not None and right.identity is not None:
        shared_action_keys = {
            key
            for key in left.event_keys & right.event_keys
            if key.startswith(
                (
                    "apple-os-release-wave:",
                    "canonical-apple-action:",
                    "structured-assertion:",
                )
            )
        }
        if (
            (left.identity.content_form == "roundup")
            != (right.identity.content_form == "roundup")
            and not (left.exact_facets & right.exact_facets)
            and not shared_action_keys
        ):
            return True
        left_services = left.identity.title_products & FIRST_PARTY_SERVICE_PRODUCTS
        right_services = right.identity.title_products & FIRST_PARTY_SERVICE_PRODUCTS
        if (
            left_services
            and right_services
            and left_services.isdisjoint(right_services)
            and not (left.exact_facets & right.exact_facets)
        ):
            return True
    left_release = {
        key for key in left.event_keys if key.startswith("apple-os-release-wave:")
    }
    right_release = {
        key for key in right.event_keys if key.startswith("apple-os-release-wave:")
    }
    left_features = {
        key for key in left.event_keys if key.startswith("apple-os-feature-scope:")
    }
    right_features = {
        key for key in right.event_keys if key.startswith("apple-os-feature-scope:")
    }
    shared_non_os_keys = {
        key
        for key in left.event_keys & right.event_keys
        if not key.startswith(("apple-os-release-wave:", "apple-os-feature-scope:"))
    }
    if (
        not shared_non_os_keys
        and ((left_release and right_features) or (right_release and left_features))
    ):
        return True
    shared_boundaries = left.boundary_keys & right.boundary_keys
    if shared_boundaries and left.event_keys and right.event_keys and not (left.event_keys & right.event_keys):
        return True
    if bool(left.hard_boundary) != bool(right.hard_boundary):
        hard_boundary = left.hard_boundary or right.hard_boundary
        if hard_boundary == "independent-third-party-action":
            return True
        if not (left.event_keys & right.event_keys):
            return True
    return False


def _explicit_property_value_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    """Contradictory property values outrank an otherwise shared quantity."""
    left_values = {key for key in left.separation_keys if key.startswith("finish-alternatives:")}
    right_values = {key for key in right.separation_keys if key.startswith("finish-alternatives:")}
    return bool(left_values and right_values and left_values.isdisjoint(right_values))


def _weak_editorial_profile(profile: ReconciliationProfile) -> bool:
    identity = profile.identity
    return bool(
        profile.relevance_tier == "weak"
        and not profile.trusted_direct_action
        and identity is not None
        and identity.content_form
        in {
            "analysis",
            "buying_advice",
            "deal",
            "hands_on",
            "podcast",
            "review",
            "roundup",
            "third_party_spotlight",
            "tutorial",
            "user_anecdote",
        }
    )


def _near_identifier(left_value: str, right_value: str) -> bool:
    if left_value == right_value:
        return True
    if min(len(left_value), len(right_value)) < 6:
        return False
    if abs(len(left_value) - len(right_value)) > 1:
        return False
    shorter, longer = sorted((left_value, right_value), key=len)
    if len(shorter) == len(longer):
        return sum(a != b for a, b in zip(shorter, longer)) <= 1
    mismatch = 0
    short_index = 0
    for character in longer:
        if short_index < len(shorter) and shorter[short_index] == character:
            short_index += 1
            continue
        mismatch += 1
        if mismatch > 1:
            return False
    return True


def _same_named_report_concrete_action(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    """Match one report's same product action despite translated detail bounds.

    A report can be summarized as "through 2027" by one publisher and "until
    at least 2028" by another. The differing bound is a fact to preserve, not a
    different event, when both articles name the same report owner and share a
    title-owned product/action relation. Report identity alone is never enough.
    """
    if left.identity is None or right.identity is None:
        return False
    left_attributions = {
        component
        for component in left.identity.components
        if component.startswith("report-attribution:")
    }
    right_attributions = {
        component
        for component in right.identity.components
        if component.startswith("report-attribution:")
    }
    if not (left_attributions & right_attributions):
        return False
    if any(key.startswith("source-action:apple-hardware-shipments:") for key in left.event_keys & right.event_keys):
        return True
    shared_actions = {
        key
        for key in left.event_keys & right.event_keys
        if key.startswith("structured-roadmap-action:")
        and key.count(":") == 2
    }
    if not shared_actions:
        return False
    shared_products = {
        key
        for key in left.separation_keys & right.separation_keys
        if key.startswith(("product-family:", "product-model:"))
    }
    return bool(shared_products)


def _projection_scope_conflict(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    """Keep aggregate-report projections out of focused action events."""
    left_projection = any(
        key.startswith("projection-child:") for key in left.separation_keys
    )
    right_projection = any(
        key.startswith("projection-child:") for key in right.separation_keys
    )
    return left_projection != right_projection


def _explicit_separation_conflict(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    """Keep explicit product/action boundaries authoritative during reunion."""
    if _disclosed_build_conflict(left, right):
        return True
    if _projection_scope_conflict(left, right):
        # A child projected from an aggregate report keeps that report's broad
        # action boundary. One overlapping product fact must not let a focused
        # launch, production, price, or feature report bridge into the cohort.
        return True
    if _same_named_report_concrete_action(left, right):
        return False
    shared_projection_lineage = {
        key
        for key in left.event_keys & right.event_keys
        if key.startswith("projection-lineage:")
    }
    if shared_projection_lineage:
        # The aggregate-parent cohort and generated child boundary agree.
        # Different changed objects are complementary facts from the same
        # projected action, not evidence of separate events.
        return False
    shared_product_roadmaps = {
        key
        for key in left.event_keys & right.event_keys
        if key.startswith("apple-roadmap:") and key.count(":") == 1
    }
    # A family roadmap key cannot erase the concrete operation already
    # bound in both sources. Proven shared reports are handled above.
    if shared_product_roadmaps and not all(
            any(key.startswith('primary-claim-predicate:') for key in profile.separation_keys)
            for profile in (left, right)):
        return False
    for disclosure, other in ((left, right), (right, left)):
        if (
            "primary-claim-predicate:finish-lineup-disclosure" in disclosure.separation_keys
            and "primary-claim-predicate:finish-lineup-disclosure" not in other.separation_keys
            and other.identity is not None
            and (
                "product-launch" in other.identity.title_actions
                or "predicate:hardware-product-roadmap" in other.separation_keys
            )
        ):
            return True
    left_content_titles = {
        key.removeprefix("content-title:")
        for key in left.separation_keys
        if key.startswith("content-title:")
    }
    right_content_titles = {
        key.removeprefix("content-title:")
        for key in right.separation_keys
        if key.startswith("content-title:")
    }
    related_content_title = any(
        _near_identifier(left_title, right_title)
        for left_title in left_content_titles
        for right_title in right_content_titles
    )
    if related_content_title:
        content_actions = {
            key.removeprefix("content-action:")
            for key in left.separation_keys | right.separation_keys
            if key.startswith("content-action:")
        }
        if content_actions <= {"new-project", "premiere-schedule"}:
            return False

    def market_regions(profile: ReconciliationProfile) -> set[str]:
        return {
            key.split(":", 4)[2]
            for key in profile.event_keys
            if key.startswith(("structured-market-result:", "structured-market-forecast:"))
            and len(key.split(":", 4)) == 5
        }

    left_market_regions = market_regions(left)
    right_market_regions = market_regions(right)
    if (
        left_market_regions
        and right_market_regions
        and left_market_regions.isdisjoint(right_market_regions)
    ):
        return True
    shared_release_keys = {
        key
        for key in left.event_keys & right.event_keys
        if key.startswith(("apple-os-release-wave:", "apple-os-platform-release-wave:"))
    }
    if (
        shared_release_keys
        and "predicate:os-release-announcement" in left.separation_keys
        and "predicate:os-release-announcement" in right.separation_keys
    ):
        return False
    left_facility_assertions = {
        key
        for key in left.event_keys
        if key.startswith("structured-assertion:apple-facility:")
    }
    right_facility_assertions = {
        key
        for key in right.event_keys
        if key.startswith("structured-assertion:apple-facility:")
    }
    if bool(left_facility_assertions) != bool(right_facility_assertions):
        return True
    shared_assertions = {
        key
        for key in left.event_keys & right.event_keys
        if key.startswith("structured-assertion:")
    }
    if shared_assertions:
        return False

    def pending_order_predicates(profile: ReconciliationProfile) -> set[str]:
        return {
            key.removeprefix("primary-claim-predicate:")
            for key in profile.separation_keys
            if key.startswith("primary-claim-predicate:pending-order-")
        }

    left_pending_order = pending_order_predicates(left)
    right_pending_order = pending_order_predicates(right)
    if left_pending_order != right_pending_order and (
        left_pending_order or right_pending_order
    ):
        return True
    for namespace in (
        "assertion-subject:",
        "assertion-action:",
        "content-title:",
        "content-action:",
        "os-feature-subject:",
        "primary-claim-subject:",
        "primary-claim-predicate:",
        "primary-claim-qualifier:",
        "projection-child:",
        "changed-object:",
        "finish-alternatives:",
        "product-family:",
        "product-model:",
        "roadmap-period:",
        "legal-party:",
        "market-report-scope:",
    ):
        left_values = {
            key for key in left.separation_keys if key.startswith(namespace)
        }
        right_values = {
            key for key in right.separation_keys if key.startswith(namespace)
        }
        if left_values and right_values and left_values.isdisjoint(right_values):
            return True
    left_assertion_actions = {
        key.removeprefix("assertion-action:")
        for key in left.separation_keys
        if key.startswith("assertion-action:")
    }
    right_assertion_actions = {
        key.removeprefix("assertion-action:")
        for key in right.separation_keys
        if key.startswith("assertion-action:")
    }
    left_title_actions = {
        key.removeprefix("action:")
        for key in left.separation_keys
        if key.startswith("action:")
    }
    right_title_actions = {
        key.removeprefix("action:")
        for key in right.separation_keys
        if key.startswith("action:")
    }
    left_predicates = {
        key.removeprefix("predicate:")
        for key in left.separation_keys
        if key.startswith("predicate:")
    }
    right_predicates = {
        key.removeprefix("predicate:")
        for key in right.separation_keys
        if key.startswith("predicate:")
    }
    if (
        "hardware-product-roadmap" in left_predicates
        and "platform-feature-change" in right_predicates
    ) or (
        "hardware-product-roadmap" in right_predicates
        and "platform-feature-change" in left_predicates
    ):
        # A shared device-family token is not an event identity. Physical
        # product planning and a platform feature change remain separate unless
        # an exact structured assertion already proved the same concrete action.
        return True
    for claim_status, generic_projection in ((left, right), (right, left)):
        if (
            "claim-status" in {
                key.removeprefix("predicate:")
                for key in claim_status.separation_keys
                if key.startswith("predicate:")
            }
            and "claim-status" not in {
                key.removeprefix("predicate:")
                for key in generic_projection.separation_keys
                if key.startswith("predicate:")
            }
            and generic_projection.identity is not None
            and "roadmap-projection" in generic_projection.identity.title_components
        ):
            # A generated product child describes the parent's current roadmap
            # facts.  It cannot absorb a separate report that explicitly says a
            # project was cancelled, retained, or otherwise changed status.
            return True
    lifecycle_action = "product-lifecycle-obsolete"
    if (
        lifecycle_action in left_assertion_actions
        and lifecycle_action not in right_assertion_actions
    ) or (
        lifecycle_action in right_assertion_actions
        and lifecycle_action not in left_assertion_actions
    ):
        return True
    return False


def _release_wave_parts(key: str) -> tuple[str, str, str]:
    value = key.removeprefix("apple-os-release-wave:")
    parts = value.split(":", 2)
    version, stage = parts[:2]
    return version, stage, parts[2] if len(parts) == 3 else ""


def _release_waves_conflict(
    left_release: set[str],
    right_release: set[str],
) -> bool:
    if not left_release or not right_release or not left_release.isdisjoint(right_release):
        return False
    return not all(
        left_stage == right_stage
        and (
            left_version == right_version
            or left_version.startswith(f"{right_version}.")
            or right_version.startswith(f"{left_version}.")
        )
        for left_key in left_release
        for right_key in right_release
        for left_version, left_stage, left_platform in [_release_wave_parts(left_key)]
        for right_version, right_stage, right_platform in [_release_wave_parts(right_key)]
    )


def _profile_release_stages(profile: ReconciliationProfile) -> set[str]:
    stages: set[str] = set()
    for key in profile.event_keys:
        if key.startswith("apple-os-release-wave:"):
            _version, stage, _platform = _release_wave_parts(key)
            stages.add(stage)
        elif key.startswith("apple-os-platform-release-wave:"):
            _platform, stage = key.removeprefix(
                "apple-os-platform-release-wave:"
            ).split(":", 1)
            stages.add(stage)
    return stages


def _profile_release_channels(profile: ReconciliationProfile) -> set[str]:
    identity = profile.identity
    if identity is None:
        return set()
    return {
        component.removeprefix("os-release-channel:")
        for component in identity.components
        if component.startswith("os-release-channel:")
    }


def _profile_release_conflict(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    if _disclosed_build_conflict(left, right):
        return True
    left_release = {
        key for key in left.event_keys if key.startswith("apple-os-release-wave:")
    }
    right_release = {
        key for key in right.event_keys if key.startswith("apple-os-release-wave:")
    }
    if _release_waves_conflict(left_release, right_release):
        return True
    left_stages = _profile_release_stages(left)
    right_stages = _profile_release_stages(right)
    if left_stages and right_stages and left_stages.isdisjoint(right_stages):
        return True
    left_channels = _profile_release_channels(left)
    right_channels = _profile_release_channels(right)
    return bool(
        left_channels
        and right_channels
        and left_channels.isdisjoint(right_channels)
    )


def _seed_profiles_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    """Return only conflicts strong enough to split an accepted seed event."""
    if _direct_title_subject_conflict(left, right):
        return True
    if _direct_title_action_conflict(left, right):
        return True
    if _weak_editorial_profile(left) != _weak_editorial_profile(right):
        return True
    if bool(left.hard_boundary) != bool(right.hard_boundary):
        hard_boundary = left.hard_boundary or right.hard_boundary
        if hard_boundary == "independent-third-party-action":
            return True
    catalog_lifecycle_key = (
        "primary-claim:apple-product-catalog:multi-product-withdrawal-forecast"
    )
    if (catalog_lifecycle_key in left.event_keys) != (
        catalog_lifecycle_key in right.event_keys
    ):
        # A catalog-wide withdrawal is one aggregate lifecycle action. Product
        # names in its enumerated list cannot attach it to a single-model
        # launch, specification, or availability story before exact reunion.
        return True
    if (
        left.relevance_tier == "weak"
        and right.relevance_tier == "weak"
        and left.identity is not None
        and right.identity is not None
        and left.identity.scope == "third-party-context"
        and right.identity.scope == "third-party-context"
        and not (left.event_keys & right.event_keys)
        and not (left.exact_facets & right.exact_facets)
    ):
        left_specific_subjects = (
            left.identity.named_subjects
            | left.identity.actors
            | left.identity.counterparties
        ) - left.identity.title_products
        right_specific_subjects = (
            right.identity.named_subjects
            | right.identity.actors
            | right.identity.counterparties
        ) - right.identity.title_products
        if not (left_specific_subjects & right_specific_subjects):
            return True
    if _explicit_separation_conflict(left, right):
        return True
    broad_roadmap_key = "primary-claim-predicate:broad-hardware-roadmap"
    left_broad_roadmap = broad_roadmap_key in left.separation_keys
    right_broad_roadmap = broad_roadmap_key in right.separation_keys
    if left_broad_roadmap != right_broad_roadmap:
        concrete = right if left_broad_roadmap else left
        if any(
            key.startswith("structured-roadmap-action:")
            for key in concrete.event_keys
        ):
            # A family-level roadmap is an aggregate source action. It cannot
            # absorb a report whose headline asserts one concrete cancellation,
            # retention, or launch merely because both discuss display panels.
            return True
    campaign_prefixes = ("apple-event-campaign:", "apple-event-occurrence:")
    left_event_campaigns = {
        key for key in left.event_keys if key.startswith(campaign_prefixes)
    }
    right_event_campaigns = {
        key for key in right.event_keys if key.startswith(campaign_prefixes)
    }
    if bool(left_event_campaigns) != bool(right_event_campaigns):
        # A campaign announcement or official campaign asset is not the same
        # action as a survey, rumor, buying guide, or product forecast that
        # happens to mention the products expected at that event.
        companion = right if left_event_campaigns else left
        if (
            "primary-claim-predicate:event-schedule-announcement"
            not in companion.separation_keys
        ):
            return True
    left_legal_stages = {
        key for key in left.separation_keys if key.startswith("legal-stage:")
    }
    right_legal_stages = {
        key for key in right.separation_keys if key.startswith("legal-stage:")
    }
    if (
        left_legal_stages
        and right_legal_stages
        and left_legal_stages.isdisjoint(right_legal_stages)
        and not (
            left.event_keys
            & right.event_keys
            & {
                "primary-claim:apple-openai-trade-secret-case:evidence-disclosure"
            }
        )
    ):
        return True
    left_firmware = {
        key for key in left.boundary_keys if key.startswith("apple-firmware:")
    }
    right_firmware = {
        key for key in right.boundary_keys if key.startswith("apple-firmware:")
    }
    if bool(left_firmware) != bool(right_firmware):
        other = right if left_firmware else left
        other_identity = other.identity
        if other_identity is not None and "airpods" not in other_identity.title_products:
            return True
    left_release = {
        key for key in left.event_keys if key.startswith("apple-os-release-wave:")
    }
    right_release = {
        key for key in right.event_keys if key.startswith("apple-os-release-wave:")
    }
    if _profile_release_conflict(left, right):
        return True
    if left.identity is not None and right.identity is not None:
        left_form = left.identity.content_form
        right_form = right.identity.content_form
        shared_action_keys = {
            key
            for key in left.event_keys & right.event_keys
            if key.startswith(
                (
                    "apple-os-release-wave:",
                    "canonical-apple-action:",
                    "structured-assertion:",
                )
            )
        }
        if (
            (left_form == "roundup") != (right_form == "roundup")
            and not (left.exact_facets & right.exact_facets)
            and not shared_action_keys
        ):
            return True
        left_services = left.identity.title_products & FIRST_PARTY_SERVICE_PRODUCTS
        right_services = right.identity.title_products & FIRST_PARTY_SERVICE_PRODUCTS
        if (
            left_services
            and right_services
            and left_services.isdisjoint(right_services)
            and not (left.exact_facets & right.exact_facets)
        ):
            return True
    left_primary_subjects = {
        key
        for key in left.boundary_keys
        if key.startswith("primary-claim-subject:")
    }
    right_primary_subjects = {
        key
        for key in right.boundary_keys
        if key.startswith("primary-claim-subject:")
    }
    left_event_schedule = (
        "primary-claim-predicate:event-schedule-announcement"
        in left.separation_keys
    )
    right_event_schedule = (
        "primary-claim-predicate:event-schedule-announcement"
        in right.separation_keys
    )
    if left_event_schedule != right_event_schedule and not (left.event_keys & right.event_keys):
        companion = right if left_event_schedule else left
        if companion.identity is not None and companion.identity.title_products:
            return True
    if (
        left_primary_subjects
        and right_primary_subjects
        and left_primary_subjects.isdisjoint(right_primary_subjects)
        and not (left.event_keys & right.event_keys)
    ):
        return True
    left_os_features = {
        key
        for key in left.event_keys
        if key.startswith("apple-os-feature-scope:")
    }
    right_os_features = {
        key
        for key in right.event_keys
        if key.startswith("apple-os-feature-scope:")
    }
    if (
        ((left_primary_subjects and right_os_features)
         or (right_primary_subjects and left_os_features))
        and not (left.event_keys & right.event_keys)
    ):
        return True
    if left_primary_subjects != right_primary_subjects and not (left.event_keys & right.event_keys):
        categories = {
            left.category_hint or left.observed_category,
            right.category_hint or right.observed_category,
        }
        if (
            categories == {"hardware_products", "software_systems"}
            and not (left.exact_facets & right.exact_facets)
        ):
            return True
    left_generic_roadmap = any(
        re.fullmatch(r"structured-canonical-title:apple .+ roadmap update", key)
        for key in left.event_keys
    )
    right_generic_roadmap = any(
        re.fullmatch(r"structured-canonical-title:apple .+ roadmap update", key)
        for key in right.event_keys
    )
    if (
        left_generic_roadmap != right_generic_roadmap
        and not (left.event_keys & right.event_keys)
    ):
        concrete = right if left_generic_roadmap else left
        concrete_primary_subjects = (
            right_primary_subjects if left_generic_roadmap else left_primary_subjects
        )
        if (
            concrete_primary_subjects
            or (concrete.category_hint or concrete.observed_category)
            and (concrete.category_hint or concrete.observed_category)
            != (
                (left.category_hint or left.observed_category)
                if left_generic_roadmap
                else (right.category_hint or right.observed_category)
            )
        ):
            return True
    if left.exact_facets & right.exact_facets:
        return False
    if left.event_keys & right.event_keys:
        return False
    left_assertions = {
        key for key in left.event_keys if key.startswith("structured-assertion:")
    }
    right_assertions = {
        key for key in right.event_keys if key.startswith("structured-assertion:")
    }
    if left_assertions and right_assertions and left_assertions.isdisjoint(right_assertions):
        return True
    left_features = {
        key for key in left.event_keys if key.startswith("apple-os-feature-scope:")
    }
    right_features = {
        key for key in right.event_keys if key.startswith("apple-os-feature-scope:")
    }
    left_roundups = {
        key for key in left.event_keys if key.startswith("apple-os-feature-roundup:")
    }
    right_roundups = {
        key for key in right.event_keys if key.startswith("apple-os-feature-roundup:")
    }
    if bool(left_release) != bool(right_release):
        non_release = right if left_release else left
        if (
            non_release.identity is not None
            and non_release.identity.actions
            & {"legal", "regulation", "security", "transaction"}
            and not (left.event_keys & right.event_keys)
        ):
            return True
    if (left_release and right_features) or (right_release and left_features):
        return True
    if (
        (left_roundups and (right_release or right_features))
        or (right_roundups and (left_release or left_features))
    ):
        return True
    if bool(left.hard_boundary) != bool(right.hard_boundary):
        hard_boundary = left.hard_boundary or right.hard_boundary
        if hard_boundary == "independent-third-party-action":
            return True
        if not (left.event_keys & right.event_keys):
            return True
    if left.identity is not None and right.identity is not None:
        left_identity = left.identity
        right_identity = right.identity
        shared_specific_subject = bool(
            (left_identity.named_subjects & right_identity.named_subjects)
            or (left_identity.counterparties & right_identity.counterparties)
            or (left_identity.case_topics & right_identity.case_topics)
            or (left_identity.title_products & right_identity.title_products)
        )
        if "legal" in left_identity.actions & right_identity.actions:
            left_legal_subjects = (
                left_identity.named_subjects
                | left_identity.counterparties
                | left_identity.case_topics
                | left_identity.title_products
            )
            right_legal_subjects = (
                right_identity.named_subjects
                | right_identity.counterparties
                | right_identity.case_topics
                | right_identity.title_products
            )
            if (
                left_legal_subjects
                and right_legal_subjects
                and left_legal_subjects.isdisjoint(right_legal_subjects)
            ):
                return True
        high_signal_actions = {"legal", "regulation", "security", "transaction"}
        left_actions = left_identity.actions & high_signal_actions
        right_actions = right_identity.actions & high_signal_actions
        if (
            left_actions
            and right_actions
            and left_actions.isdisjoint(right_actions)
            and not shared_specific_subject
            and not (left.event_keys & right.event_keys)
            and not (left.exact_facets & right.exact_facets)
        ):
            return True
    left_policy_boundaries = {
        key for key in left.boundary_keys if key.startswith("apple-platform-policy:")
    }
    right_policy_boundaries = {
        key for key in right.boundary_keys if key.startswith("apple-platform-policy:")
    }
    left_incident_boundaries = {
        key for key in left.boundary_keys if key.startswith("structured-subject:")
    }
    right_incident_boundaries = {
        key for key in right.boundary_keys if key.startswith("structured-subject:")
    }
    if (
        (
            left_policy_boundaries
            and right_incident_boundaries
            or right_policy_boundaries
            and left_incident_boundaries
        )
        and not (left.event_keys & right.event_keys)
        and not (left.exact_facets & right.exact_facets)
    ):
        return True
    if (
        left.hard_boundary
        and right.hard_boundary
        and left.hard_boundary != right.hard_boundary
        and not (left.event_keys & right.event_keys)
    ):
        return True
    left_os_scopes = {
        boundary
        for boundary in left.boundary_keys
        if boundary.startswith("apple-os-feature-scope:")
    }
    right_os_scopes = {
        boundary
        for boundary in right.boundary_keys
        if boundary.startswith("apple-os-feature-scope:")
    }
    if left_os_scopes and right_os_scopes and left_os_scopes.isdisjoint(right_os_scopes):
        return True
    for namespace in (
        "title-fact:",
        "product-family:",
        "product-model:",
        "legal-party:",
        "legal-stage:",
        "action:",
        "predicate:",
        "weak-topic:",
    ):
        left_values = {
            key for key in left.separation_keys if key.startswith(namespace)
        }
        right_values = {
            key for key in right.separation_keys if key.startswith(namespace)
        }
        if left_values and right_values and left_values.isdisjoint(right_values):
            return True
    shared_boundaries = left.boundary_keys & right.boundary_keys
    staged_boundaries = {
        boundary
        for boundary in shared_boundaries
        if boundary.startswith(("app-store-removal:", "apple-legal-case:", "apple-legal-party:"))
    }
    return bool(
        staged_boundaries
        and left.event_keys
        and right.event_keys
        and not (left.event_keys & right.event_keys)
    )


def _event_key_namespace(key: str) -> str:
    for prefix in (
        "structured-first-party-subject:",
        "structured-attributed-measure:",
        "structured-component-measure:",
        "structured-component-period:",
        "structured-entity-component:",
        "structured-legal-settlement:",
        "structured-claim-status:",
        "structured-market-result:",
        "structured-market-forecast:",
        "structured-subject-product:",
        "structured-subject-action:",
        "structured-component:",
        "structured-report:",
        "apple-os-release-wave:",
        "apple-os-platform-release-wave:",
        "apple-os-feature-roundup:",
        "apple-os-feature-scope:",
    ):
        if key.startswith(prefix):
            return prefix
    return key.split(":", 1)[0] + ":"


def supported_reconciliation_event_keys(
    profiles: Sequence[ReconciliationProfile],
) -> set[str]:
    """Return exact keys supported by a coherent, possibly sparse source group."""
    union = {key for profile in profiles for key in profile.event_keys}
    supported: set[str] = set()
    for key in union:
        if key.startswith(("apple-event-campaign:", "apple-event-occurrence:")):
            if all(
                any(
                    candidate.startswith(
                        ("apple-event-campaign:", "apple-event-occurrence:")
                    )
                    for candidate in profile.event_keys
                )
                for profile in profiles
            ):
                supported.add(key)
            continue
        if key.startswith("structured-canonical-title:"):
            if all(key in profile.event_keys for profile in profiles):
                supported.add(key)
            continue
        if key.startswith("apple-os-release-wave:"):
            conflicting = any(
                {
                    candidate
                    for candidate in profile.event_keys
                    if candidate.startswith("apple-os-release-wave:")
                }
                and key not in profile.event_keys
                for profile in profiles
            )
            if not conflicting:
                supported.add(key)
            continue
        if key.startswith("structured-"):
            if key.startswith(STRUCTURED_EVIDENCE_KEY_PREFIXES):
                supported.add(key)
                continue
            namespace = _event_key_namespace(key)
            if all(
                not {
                    candidate
                    for candidate in profile.event_keys
                    if _event_key_namespace(candidate) == namespace
                }
                or key in profile.event_keys
                for profile in profiles
            ):
                supported.add(key)
            continue
        if key.startswith("primary-claim:"):
            namespace = _event_key_namespace(key)
            if all(
                not {
                    candidate
                    for candidate in profile.event_keys
                    if _event_key_namespace(candidate) == namespace
                }
                or key in profile.event_keys
                for profile in profiles
            ):
                supported.add(key)
            continue
        if all(not profile.event_keys or key in profile.event_keys for profile in profiles):
            supported.add(key)
    return supported



def _explicit_identity_conflict(
    left_profile: ReconciliationProfile,
    right_profile: ReconciliationProfile,
) -> bool:
    left = left_profile.identity
    right = right_profile.identity
    if left is None or right is None:
        return False
    shared_event_keys = left_profile.event_keys & right_profile.event_keys
    if any(
        key.startswith("primary-claim:apple-")
        and key.endswith(":schedule-forecast")
        for key in shared_event_keys
    ):
        # Product lineups are supporting facts in event-date coverage. Two
        # reports may name different subsets of the same launch slate while
        # asserting the same event schedule.
        return False
    left_generations = {
        component
        for component in left.title_components
        if component.startswith("product-generation:")
    }
    right_generations = {
        component
        for component in right.title_components
        if component.startswith("product-generation:")
    }
    if (
        left_generations
        and right_generations
        and left_generations.isdisjoint(right_generations)
    ):
        return True
    left_foldable = "foldable-iphone" in left.title_products
    right_foldable = "foldable-iphone" in right.title_products
    if left_foldable != right_foldable and (
        left_generations or right_generations
    ):
        return True
    left_is_analyst_action = "analyst-target-action" in left.title_components
    right_is_analyst_action = "analyst-target-action" in right.title_components
    if left_is_analyst_action != right_is_analyst_action:
        return True
    def predicate_classes(identity: EventIdentity) -> set[str]:
        title_components = identity.title_components
        if "component-cost-analysis" in title_components:
            return {"component-cost-analysis"}
        if "immersive-live-video" in identity.components:
            return {"immersive-live-content"}
        if "apple-tv-sports-schedule" in (
            left_profile.exact_facets if identity is left else right_profile.exact_facets
        ):
            return {"content-schedule"}
        if title_components & {"display-panel", "oled-display"}:
            return {"component-development"}
        if title_components & {"hardware-market-performance", "memory-supply"}:
            return {"supply-or-shipment-outlook"}
        product_specific = any(
            component.startswith(
                (
                    "apple-silicon-generation:",
                    "iphone-family:",
                    "iphone-model:",
                    "macbook-model:",
                    "product-generation:",
                )
            )
            for component in title_components
        )
        if (
            product_specific
            and identity.title_actions & {"delay-roadmap", "feature-change", "pilot-testing"}
        ):
            return {"product-roadmap"}
        return set()

    left_components = predicate_classes(left)
    right_components = predicate_classes(right)
    predicate_conflict = bool(
        left_components
        and right_components
        and left_components.isdisjoint(right_components)
    )
    if predicate_conflict:
        authoritative_shared_keys = {
            key
            for key in shared_event_keys
            if not (
                ":multi-" in key
                or ":product-segment:" in key
                or key.endswith(":market-summary")
            )
        }
        return not authoritative_shared_keys
    if shared_event_keys:
        return False
    if left_profile.exact_facets & right_profile.exact_facets:
        return False
    return False




def _campaign_calendar_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    # A name and a date are different identity dimensions. A real source may
    # link them, so missing dimensions are not contradictory campaign names.
    for prefix in ("apple-event-campaign:", "apple-event-occurrence:", "apple-event-year:",
                   "apple-event-calendar:beijing:", "apple-event-calendar:event-local:",
                   "apple-event-calendar:unspecified:"):
        left_values = {key for key in left.event_keys if key.startswith(prefix)}
        right_values = {key for key in right.event_keys if key.startswith(prefix)}
        if left_values and right_values and left_values.isdisjoint(right_values):
            return True
    return False


def profile_pair_decision(left: ReconciliationProfile, right: ReconciliationProfile) -> MergeDecision:
    """One pair boundary for explicit source claims and existing positive evidence."""
    for excluded, current in ((left, right), (right, left)):
        if (excluded.relevance_tier == "weak" and current.relevance_tier in {"strong", "ecosystem"}
                and (excluded.defer_reason == "third-party hardware comparison with Apple products"
                     or "source-form:editorial-hardware-inference" in excluded.separation_keys)):
            # A shared configuration key cannot undo a demonstrated
            # different owner or absence of current reporting.
            return "conflict"
    if left.identity is not None and right.identity is not None:
        if (("claim-polarity:configuration-denied" in left.identity.title_components)
                != ("claim-polarity:configuration-denied" in right.identity.title_components)):
            return "conflict"
    if _source_object_conflict(left, right):
        return "conflict"
    lifecycle_years = []
    for profile in (left, right):
        years: dict[str, set[str]] = {}
        for key in profile.separation_keys:
            if key.startswith("lifecycle-model-year:"):
                _, family, year = key.split(":", 2)
                years.setdefault(family, set()).add(year)
        lifecycle_years.append(years)
    for family in lifecycle_years[0].keys() & lifecycle_years[1].keys():
        if lifecycle_years[0][family].isdisjoint(lifecycle_years[1][family]):
            return "conflict"
    for prefix in ("event-operation-action:", "retail-trade-in-action:", "benchmark-report-action:", "clock-workday-region:", "source-report-period:", "source-report-year:", "source-report-region:", "source-model-generation:", "source-launch-stage:"):
        left_actions = {key for key in left.separation_keys if key.startswith(prefix)}
        right_actions = {key for key in right.separation_keys if key.startswith(prefix)}
        if left_actions and right_actions and left_actions.isdisjoint(right_actions):
            return "conflict"
    teardown_parts = []
    for profile in (left, right):
        parts = {}
        for key in profile.separation_keys:
            if key.startswith("teardown-part-code:"):
                _, family, value = key.split(":", 2)
                parts.setdefault(family, set()).add(value)
        teardown_parts.append(parts)
    for family in teardown_parts[0].keys() & teardown_parts[1].keys():
        if teardown_parts[0][family].isdisjoint(teardown_parts[1][family]):
            return "conflict"
    part_numbers = [{key for key in profile.separation_keys if key.startswith("teardown-part-number:")} for profile in (left, right)]
    if all(part_numbers) and part_numbers[0].isdisjoint(part_numbers[1]):
        return "conflict"
    launch_subjects = [{key.removeprefix('source-launch-subject:') for key in profile.separation_keys
                        if key.startswith('source-launch-subject:')} for profile in (left, right)]
    def contains_launch_subject(family, model):
        if family in {'iphone', 'ipad', 'macbook', 'homepod', 'airpods', 'apple-watch'}:
            return model.startswith(family + '-')
        if family.startswith('iphone-family-'):
            return model.startswith('iphone-' + family.removeprefix('iphone-family-') + '-')
        return False
    if all(launch_subjects) and not any(a == b or contains_launch_subject(a, b) or contains_launch_subject(b, a)
                                      for a in launch_subjects[0] for b in launch_subjects[1]):
        return 'conflict'
    if _campaign_calendar_conflict(left, right):
        return "conflict"
    if left.bound_claim is not None or right.bound_claim is not None:
        if left.bound_claim is None or right.bound_claim is None:
            return "unknown"
        return identity_pair_decision(left.bound_claim, right.bound_claim)
    if left.identity is not None and right.identity is not None and _price_object_conflict(left.identity, right.identity):
        return "conflict"
    launch_windows = []
    for profile in (left, right):
        launch_windows.append({parts[1]: parts[2:] for key in profile.separation_keys
                               if key.startswith("hardware-launch-window:")
                               for parts in [key.split(":")]})
    for product in launch_windows[0].keys() & launch_windows[1].keys():
        first, second = launch_windows[0][product], launch_windows[1][product]
        # An unknown year cannot invent a year conflict, but it does not
        # erase an explicit month constraint. Compare closed windows by their
        # calendar months when only one source supplies a year.
        if (first[0] == "unspecified") != (second[0] == "unspecified"):
            if first[2] != "open" and second[2] != "open":
                months = [{(month - 1) % 12 for month in range(int(window[1]), int(window[2]) + 1)}
                          for window in (first, second)]
                if months[0].isdisjoint(months[1]):
                    return "conflict"
            continue
        bounds = []
        for year, lower, upper in (first, second):
            offset = 0 if year == "unspecified" else int(year) * 12
            bounds.append((offset + int(lower), float("inf") if upper == "open" else offset + int(upper)))
        if max(bounds[0][0], bounds[1][0]) > min(bounds[0][1], bounds[1][1]):
            return "conflict"
    for prefix in ("spotlight-execution:", "spotlight-target:"):
        values = [{key for key in profile.separation_keys if key.startswith(prefix)} for profile in (left, right)]
        if all(values) and values[0].isdisjoint(values[1]):
            return "conflict"
    accessory_refresh_support = False
    refreshes = [{key.split(":")[1]: key.split(":")[2] for key in profile.separation_keys
                  if key.startswith("source-accessory-refresh:")} for profile in (left, right)]
    for product in refreshes[0].keys() & refreshes[1].keys():
        if refreshes[0][product] != refreshes[1][product]:
            return "conflict"
        features = [{key for key in profile.event_keys
                     if key.startswith(f"canonical-apple-action:{product}:") and key.endswith("-adoption")}
                    for profile in (left, right)]
        if all(features) and features[0].isdisjoint(features[1]):
            return "conflict"
        if bool(features[0]) != bool(features[1]):
            accessory_refresh_support = True
    retail_values = []
    for profile in (left, right):
        values = {}
        for key in profile.separation_keys:
            if key.startswith("retail-offer-value:"):
                _, product, currency, amount = key.split(":", 3)
                values.setdefault((product, currency), set()).add(amount)
        retail_values.append(values)
    for item in retail_values[0].keys() & retail_values[1].keys():
        if retail_values[0][item].isdisjoint(retail_values[1][item]):
            return "conflict"
    battery_values = []
    for profile in (left, right):
        values = {}
        for key in profile.separation_keys:
            if key.startswith("battery-capacity-value:"):
                _, model, region, amount = key.split(":", 3)
                values.setdefault((model, region), set()).add(amount)
        battery_values.append(values)
    for item in battery_values[0].keys() & battery_values[1].keys():
        if battery_values[0][item].isdisjoint(battery_values[1][item]):
            return "conflict"
    camera_stages = [{key for key in profile.separation_keys if key.startswith("camera-adoption-stage:")}
                     for profile in (left, right)]
    if all(camera_stages) and camera_stages[0].isdisjoint(camera_stages[1]):
        return "conflict"
    disclosure_stages = [{key for key in profile.separation_keys if key.startswith("product-disclosure-stage:")}
                         for profile in (left, right)]
    if all(disclosure_stages) and disclosure_stages[0].isdisjoint(disclosure_stages[1]):
        return "conflict"
    preorder_stages = [{key for key in profile.separation_keys if key.startswith("preorder-stage:")}
                       for profile in (left, right)]
    if all(preorder_stages) and preorder_stages[0].isdisjoint(preorder_stages[1]):
        return "conflict"
    preview_versions = [{key for key in profile.separation_keys if key.startswith("safari-preview-version:")}
                        for profile in (left, right)]
    if all(preview_versions) and preview_versions[0].isdisjoint(preview_versions[1]):
        return "conflict"
    refurbished = ["action:official-refurbished-availability" in profile.separation_keys for profile in (left, right)]
    if any(refurbished) and not all(refurbished):
        return "conflict"
    relief_hazards = [{key for key in profile.separation_keys if key.startswith("disaster-relief-hazard:")}
                      for profile in (left, right)]
    if all(relief_hazards) and relief_hazards[0].isdisjoint(relief_hazards[1]):
        return "conflict"
    contract_ends = [{key for key in profile.separation_keys if key.startswith("supply-contract-end:")}
                     for profile in (left, right)]
    if all(contract_ends) and contract_ends[0].isdisjoint(contract_ends[1]):
        return "conflict"
    for prefix in ("market-result-stage:", "market-result-year:", "market-result-quarter:", "camera-airpods-delay-year:"):
        result_values = [{key for key in profile.separation_keys if key.startswith(prefix)} for profile in (left, right)]
        if all(result_values) and result_values[0].isdisjoint(result_values[1]):
            return "conflict"
    local_market_measures = []
    for profile in (left, right):
        measures = {}
        for key in profile.separation_keys:
            if key.startswith("market-result-local-measure:"):
                _, region, metric, value = key.split(":", 3)
                measures.setdefault((region, metric), set()).add(value)
        local_market_measures.append(measures)
    for owned_metric in local_market_measures[0].keys() & local_market_measures[1].keys():
        if local_market_measures[0][owned_metric].isdisjoint(local_market_measures[1][owned_metric]):
            return "conflict"
    market_measures = []
    for profile in (left, right):
        measures = {}
        for key in profile.separation_keys:
            if key.startswith("market-result-measure:"):
                _, metric, value = key.split(":", 2)
                measures.setdefault(metric, set()).add(value)
        market_measures.append(measures)
    if all(market_measures):
        shared_metrics = market_measures[0].keys() & market_measures[1].keys()
        if any(market_measures[0][metric].isdisjoint(market_measures[1][metric]) for metric in shared_metrics):
            return "conflict"
    leak_actions = [{key for key in profile.separation_keys if key.startswith("source-leak-action:")}
                    for profile in (left, right)]
    if all(leak_actions) and leak_actions[0].isdisjoint(leak_actions[1]):
        return "conflict"
    research_cases = [{key for key in profile.separation_keys if key.startswith("security-research-case:")}
                      for profile in (left, right)]
    if all(research_cases) and research_cases[0].isdisjoint(research_cases[1]):
        return "conflict"
    device_polarities = [{key.rsplit(":", 1)[0]: key.rsplit(":", 1)[1]
                          for key in profile.separation_keys if key.startswith("device-feature-polarity:")}
                         for profile in (left, right)]
    if any(device_polarities[0][key] != device_polarities[1][key]
           for key in device_polarities[0].keys() & device_polarities[1].keys()):
        return "conflict"
    for prefix in ("panel-report-institution:", "panel-report-year:", "tariff-arrangement-partner:", "mac-demand-speaker:", "fold-production-stage:", "battery-cell-capacities:", "battery-total-capacity:", "security-bulletin-version:", "vulnerability-component:", "vulnerability-remediation:", "device-feature-generation:", "device-feature-version:", "organization-department:", "organization-leader:", "organization-stage:", "merger-party:", "merger-stage:", "maps-ad-action:", "car-key-partner:", "car-key-stage:", "car-key-version:", "factory-investigation-owner:", "factory-investigation-action:", "content-named-event:", "content-named-event-action:", "content-event-year:", "content-production-work:", "content-production-season:", "source-current-action:", "creator-studio-action:", "beats-cable-finish:", "messages-approved-agent:", "payment-rewards-partner:", "payment-rewards-action:", "fold-launch-stage:", "fold-launch-year:", "ai-cost-service:", "ai-cost-stage:", "ai-cost-owner:",
                   "education-offer-year:", "education-offer-end:", "education-offer-stage:",
                   "app-acquisition-target:", "app-acquisition-stage:", "clinical-institution:",
                   "clinical-procedure:", "clinical-application:", "shipment-report-year:",
                   "capacity-before:", "capacity-after:", "support-list-feature:", "interview-test-duration:", "teardown-model:"):
        values = [{key for key in profile.separation_keys if key.startswith(prefix)} for profile in (left, right)]
        if all(values) and values[0].isdisjoint(values[1]):
            return "conflict"
    for capacity, cancellation in ((left, right), (right, left)):
        if (any(key.startswith("capacity-after:") for key in capacity.separation_keys)
                and cancellation.identity is not None
                and "project-cancellation" in cancellation.identity.title_actions):
            return "conflict"
    for foreign, direct in ((left, right), (right, left)):
        if (foreign.event_kind_hint == "third_party_ecosystem" and (foreign.defer_reason or foreign.relevance_tier == "weak")
                and direct.relevance_tier in {"strong", "ecosystem"}
                and direct.event_kind_hint != "third_party_ecosystem"):
            return "conflict"
    roadmap_actions = [{key.split(":")[2] for key in profile.event_keys
                        if key.startswith("structured-roadmap-action:") and key.count(":") >= 2}
                       for profile in (left, right)]
    if all(roadmap_actions) and roadmap_actions[0].isdisjoint(roadmap_actions[1]):
        return "conflict"
    for interoperability, hardware in ((left, right), (right, left)):
        if ("apple-cross-device-clipboard" in interoperability.exact_facets
                and hardware.event_kind_hint == "hardware_market"
                and "apple-cross-device-clipboard" not in hardware.exact_facets):
            return "conflict"
    content_scopes = [_content_work_profile(profile) for profile in (left, right)]
    if all(titles for titles, _ in content_scopes):
        for prefix in ("content-date:", "content-date-year:"):
            values = [{key for key in profile.separation_keys if key.startswith(prefix)} for profile in (left, right)]
            if all(values) and values[0].isdisjoint(values[1]):
                return "conflict"
        actions = content_scopes[0][1] | content_scopes[1][1]
        if actions == {"trailer", "premiere-schedule"} and not all("content-primary-premiere" in profile.separation_keys for profile in (left, right)):
            return "unknown"
    if _disclosed_build_conflict(left, right) or _explicit_property_value_conflict(left, right):
        return "conflict"
    configurations = [{key for key in profile.separation_keys if key.startswith("later-configuration:")}
                      for profile in (left, right)]
    if (any(configurations) and configurations[0] != configurations[1]
            and left.identity is not None and right.identity is not None
            and left.identity.title_products & right.identity.title_products):
        return "conflict"
    performance_versions = [{key for key in profile.separation_keys if key.startswith("platform-performance-version:")}
                            for profile in (left, right)]
    if all(performance_versions) and performance_versions[0].isdisjoint(performance_versions[1]):
        return "conflict"
    if left.identity is not None and right.identity is not None:
        finance_actions = [{key for key in profile.identity.title_components
                            if key.startswith("primary-finance-action:")} for profile in (left, right)]
        if all(finance_actions) and finance_actions[0].isdisjoint(finance_actions[1]):
            return "conflict"
        for supplier, product_report in ((left, right), (right, left)):
            if ("memory-supply" in supplier.identity.title_components
                    and "assertion-action:supplier-capacity-constraint" in supplier.separation_keys
                    and not any(key.startswith(("iphone-model:", "product-generation:")) for key in supplier.identity.title_components)
                    and "predicate:retail-price-change" in product_report.separation_keys
                    and any(key.startswith("iphone-model:") for key in product_report.identity.title_components)
                    and not _same_named_report_concrete_action(supplier, product_report)):
                return "conflict"
    keys = left.event_keys & right.event_keys
    release = any(key.startswith(("apple-os-release-wave:", "apple-os-platform-release-wave:")) for key in keys)
    assertion = any(key.startswith("structured-assertion:") for key in keys)
    canonical = any(key.startswith(("apple-event-campaign:", "apple-event-occurrence:",
                                   "canonical-apple-action:", "primary-claim:", "projection-lineage:", "apple-legal:", "apple-firmware:", "source-action:")) for key in keys)
    roadmap = any(key.startswith("structured-roadmap-action:") and len(key.split(":")) >= 4 for key in keys)
    evidence = any(key.startswith(STRUCTURED_EVIDENCE_KEY_PREFIXES) for key in keys)
    concrete_release = release and all("predicate:os-release-announcement" in profile.separation_keys for profile in (left, right))
    attributed = _same_named_report_concrete_action(left, right)
    scoped_entitlement = bool(left.exact_facets & right.exact_facets & {
        "apple-intelligence-china-regulatory-rollout", "icloud-service-perks"})
    authoritative = scoped_entitlement or canonical or assertion or roadmap or concrete_release or attributed or _compatible_content_work_profiles(left, right)
    exact_measure = any(key.startswith(("structured-measure:", "structured-component-measure:"))
                        and len(key.split(":")) >= 5 for key in keys)
    if _profile_release_conflict(left, right) or _projection_scope_conflict(left, right):
        return "conflict"
    stable_platforms = [{_release_wave_parts(key)[2] for key in profile.event_keys
                         if key.startswith('apple-os-release-wave:') and _release_wave_parts(key)[1] == 'final'}
                        for profile in (left, right)]
    # Separate platform reports need a joint release source to connect them.
    if all(stable_platforms) and stable_platforms[0].isdisjoint(stable_platforms[1]):
        return 'unknown'
    if _profiles_conflict(left, right) and not authoritative:
        return "conflict"
    if (_explicit_separation_conflict(left, right) or _seed_profiles_conflict(left, right)) and not (authoritative or exact_measure):
        return "conflict"
    identity = identity_pair_decision(left.identity, right.identity) if left.identity and right.identity else "unknown"
    if identity == "conflict" and not (release or evidence or assertion or canonical or roadmap or scoped_entitlement):
        return "conflict"
    if _explicit_identity_conflict(left, right) and not (authoritative or evidence or release):
        return "conflict"
    if all(market_measures) and not (market_measures[0].keys() & market_measures[1].keys()):
        # Complementary dimensions are not contradictory, but the generic
        # provider/period key alone cannot establish a shared report.
        return "unknown"
    # A missing release version cannot select one of several supported trains.
    # This is uncertainty, not contradictory source evidence; retain both items.
    for sparse, numbered in ((left, right), (right, left)):
        if (any(key.startswith("ambiguous-platform-stage:") for key in sparse.separation_keys)
                and any(key.startswith("apple-os-release-wave:") for key in numbered.event_keys)):
            return "unknown"
    # Retain concrete structured relations (including legal and release
    # evidence), while blocking product/topic similarity as an action bridge.
    if (any("source-local-action-authority" in p.separation_keys
                and any(key.startswith("primary-claim:") for key in p.event_keys)
                for p in (left,right))
            and not (authoritative or exact_measure
                or (left.identity is not None and right.identity is not None
                    and not any("primary-claim-predicate:joint-status-filing" in p.separation_keys
                                for p in (left, right))
                    and _legal_decision(left.identity,right.identity)=="match")
                or (evidence and any(
                not key.startswith(("structured-entity-component:", "structured-component-period:"))
                and key.startswith(STRUCTURED_EVIDENCE_KEY_PREFIXES) for key in keys)))):
        return "unknown"
    if identity == "match" or authoritative or exact_measure or accessory_refresh_support or _source_report_pair_supported(left, right):
        return "match"
    if left.exact_facets & right.exact_facets:
        return "match"
    # Product/update/disclosure labels describe the recall scope, not the
    # concrete capability or launch action owned by two separate sources.
    generic_scope_prefixes = (
        "structured-canonical-title:", "structured-entity-component:", "structured-component:",
        "structured-title-product-update:", "structured-title-product-release:",
        "structured-subject-product:", "structured-subject-action:", "structured-title-action:",
        "structured-first-party-subject:",
    )
    if keys and not all(key.startswith(generic_scope_prefixes) for key in keys):
        return "match"
    return "unknown"


def _content_work_profile(profile: ReconciliationProfile) -> tuple[set[str], set[str]]:
    titles = {
        key.removeprefix("content-title:")
        for key in profile.separation_keys
        if key.startswith("content-title:")
    }
    actions = {
        key.removeprefix("content-action:")
        for key in profile.separation_keys
        if key.startswith("content-action:")
    }
    return titles, actions


def _compatible_content_work_profiles(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    if left.identity is not None and right.identity is not None:
        identities = (left.identity, right.identity)
        shared_lifecycle = {component for component in identities[0].components & identities[1].components
                            if component.startswith("content-lifecycle:")}
        if (all("apple-tv" in identity.products for identity in identities) and shared_lifecycle
                and identities[0].named_subjects & identities[1].named_subjects):
            return True
    left_titles, left_actions = _content_work_profile(left)
    right_titles, right_actions = _content_work_profile(right)
    return bool(
        left_titles
        and right_titles
        and any(
            _near_identifier(left_title, right_title)
            for left_title in left_titles
            for right_title in right_titles
        )
        and (left_actions | right_actions <= {"new-project", "premiere-schedule"}
             or (left_actions | right_actions <= {"trailer", "premiere-schedule"}
                 and left.identity is not None and right.identity is not None
                 and "content-lifecycle:premiere" in left.identity.components & right.identity.components))
    )



def _source_report_pair_supported(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    """Specific source citation or shared generation measurements supply recall."""
    if left.identity is None or right.identity is None:
        return False
    if "source-form:editorial-hardware-inference" in left.separation_keys & right.separation_keys:
        same_product = left.identity.title_products & right.identity.title_products
        cited = any(
            "cited-source:" + key.removeprefix("report-origin:") in cited_profile.separation_keys
            for origin_profile, cited_profile in ((left, right), (right, left))
            for key in origin_profile.separation_keys if key.startswith("report-origin:"))
        if same_product and cited:
            return True
    shared_reports = {key for key in left.identity.components & right.identity.components
                      if key.startswith("report-attribution:")}
    if (shared_reports and any(key.startswith("structured-canonical-title:") for key in left.event_keys & right.event_keys)
            and all(profile.identity.scope == "apple-direct" and profile.identity.content_form == "news" for profile in (left, right))):
        return True
    generations = {key for key in left.identity.title_components & right.identity.title_components
                   if key.startswith("product-generation:")}
    if not generations:
        return False
    # Quantities from a later specification paragraph cannot override the
    # source's established action. Once either source has a concrete primary
    # relation, this fallback needs the same subject and predicate on both.
    primary_subjects = [{key for key in profile.separation_keys if key.startswith("primary-claim-subject:")}
                        for profile in (left, right)]
    primary_predicates = [{key for key in profile.separation_keys if key.startswith("primary-claim-predicate:")}
                          for profile in (left, right)]
    if any(primary_predicates) and not (primary_subjects[0] & primary_subjects[1] and primary_predicates[0] & primary_predicates[1]):
        return False
    generation_numbers = {key.rsplit("-", 1)[-1] for key in generations}
    shared = left.separation_keys & right.separation_keys
    numbers = {key.removeprefix("generation-report-token:") for key in shared
               if key.startswith("generation-report-token:")} - generation_numbers
    distinctive = {key for key in shared if key.startswith("generation-report-distinctive:")}
    return (len(numbers) >= 2 and len(distinctive) >= 4
            and any("." in token or token.endswith(("mm", "inch", "inches")) for token in numbers))
