"""Deterministic pair matching for title-led Apple news event identities."""

from __future__ import annotations

from typing import Literal

from .event_identity import CROSS_PRODUCT_IDENTITY_FACETS, UMBRELLA_FACETS, EventIdentity


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


def identity_pair_decision(left: EventIdentity, right: EventIdentity) -> MergeDecision:
    """Resolve only high-confidence identities; leave nuanced cases to legacy guards."""
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
    if (
        "apple-home-hub" in left.title_products & right.title_products
        and left.scope == "apple-direct"
        and right.scope == "apple-direct"
        and _actions_compatible(left.actions, right.actions)
        and bool((left.actions | right.actions) & {"delay-roadmap", "retail-availability"})
    ):
        return "match"

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
        "roadmap-projection" in (left.title_components | right.title_components)
        and bool(left.title_products & right.title_products)
        and "delay-roadmap" in left.actions & right.actions
    ):
        return "match"
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

    if shared_named_subjects or compatible_named_subjects:
        shared_actions = left.actions & right.actions & HIGH_SIGNAL_NAMED_SUBJECT_ACTIONS
        if shared_actions and _products_compatible(left.products, right.products):
            # A chip, executive, analyst, or other named subject found only in
            # body context is supporting evidence, not event identity. It may
            # reconcile different facet wording only when both headlines make
            # that same subject primary.
            if (
                left.facets
                and right.facets
                and not shared_facets
                and not (shared_title_named_subjects or compatible_title_named_subjects)
            ):
                return "conflict"
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
        shared_first_party_services
        and not apple_tv_content_with_title_identity
        and left.actions & right.actions & {
        "content-release",
        "market-report",
        "platform-trust",
        "price-change",
        "retail-availability",
        }
    ):
        return "match"
    concrete_components = _high_confidence_components(shared_components)
    if (
        concrete_components
        and ((left.title_components | right.title_components) & concrete_components)
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
