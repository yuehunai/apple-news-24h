"""Bounded grammatical claims whose object owns category and reconciliation.

These frames intentionally return one action, not a bag of background topics.
Names and release values come from the article, never source URLs or headlines.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .event_identity import ANALYST_INSTITUTION_ALIASES


@dataclass(frozen=True)
class PrimaryAction:
    subject: str
    predicate: str
    category: str
    tier: str = "strong"


def primary_action_domain(title: str, lead: str) -> str:
    """Negative action boundaries remain useful without a complete merge key."""
    if re.search(r"\b(?:out of stock|unavailable|sold out|inventory)\b|库存|售罄|缺货", title):
        return 'retail-inventory'
    if re.search(r"\bpatent\b|专利", title) or (
        re.search(r"\bapple\b|苹果", title)
        and re.search(r"\b(?:new|latest|granted)\s+patent\b|最新.*?专利|专利.*?显示", lead[:450])
    ):
        return 'patent-disclosure'
    return ''


def _slug(value: str) -> str:
    return re.sub(r"[^\w.+-]+", "-", value.strip()).strip("-")


def _sentences(value: str) -> list[str]:
    return re.split(r"[。！？;；]|(?<=[.!?])\s+", value)


def _app_object(value: str) -> str:
    # The release object, not a nearby platform or a later unrelated app name.
    action = re.search(
        r"(?:\b(?:introduc\w*|announc\w*|releas\w*|launch\w*)\s+|推出|发布|公布)"
        r"\s*(?:(?:its|an?|the|all-new|new|own|first-party)\s+|了|其|全新|自研|一款|新的?)*"
        r"['\"‘“]?(?P<name>[a-z][a-z0-9.+-]*(?:\s+[a-z][a-z0-9.+-]*){0,3}|[\u4e00-\u9fff]{2,10})"
        r"['\"’”]?\s*(?:app\b(?!\s+store)|application\b|应用(?!商店))", value,
    )
    return _slug(action.group('name')) if action else ''


def _apple_app_release(value: str) -> bool:
    owner = re.search(
        r"\bapple\s+(?:(?:to|plans?|may|will|has|today|just|now|reportedly)\s+)*"
        r"(?:introduc\w*|announc\w*|releas\w*|launch\w*)\b|"
        r"苹果(?:公司)?(?:或|将|拟|计划|今天|今日|刚刚|正式|已)*"
        r"(?:为[^,，。！？]{1,35})?(?:推出|发布|公布)", value,
    )
    first_action = re.search(r"\b(?:introduc\w*|announc\w*|releas\w*|launch\w*)\b|推出|发布|公布", value)
    return bool(owner and first_action and first_action.start() >= owner.start())


def _apple_firmware_actor(value: str) -> bool:
    return bool(re.search(
        r"\bapple\s+(?:(?:today|has|just|now|also)\s+)*(?:releas\w*|issu\w*|updat\w*)\b|"
        r"苹果(?:公司)?(?:今天|今日|已|同时|还|提前|刚刚)*(?:为|向|发布|推送)", value,
    ))


def _device(value: str) -> str:
    device = re.search(
        r"\b(?:beats\s*(?:[a-z0-9]+)(?:\s+(?:pro|plus|studio|buds|\d+)){0,3}|"
        r"airpods(?:\s+(?:pro|max|\d+)){0,3})\b", value,
    )
    if device:
        return _slug(device.group())
    adapter = re.search(r"(?<![a-z0-9])(\d+)\s*w\s+usb-c\s*(?:power\s*)?(?:adapter|charger|电源适配器|适配器)", value)
    return f"apple-{adapter.group(1)}w-usb-c-adapter" if adapter else ''


def _firmware_version(value: str) -> str:
    version = r"(?:\d+[a-z]\d+[a-z]?|\d+(?:\.\d+){2,})"
    # Prefer the target of an upgrade over the old version in the same clause.
    target = re.search(rf"(?:升级到|升级至|更新至)\s*v?({version})", value)
    if target:
        return target.group(1)
    for pattern in (
        rf"(?:版本号?|version|firmware)\s*[:：]?\s*v?({version})",
        rf"(?<![\w.])v?({version})\s*(?:固件|firmware)",
    ):
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return ''


def _firmware_action(title: str, lead: str) -> PrimaryAction | None:
    device = _device(title)
    if not device or device == 'airpods':
        return None
    device_pattern = re.escape(device).replace(r'\-', r'\s+')
    title_owned = _apple_firmware_actor(title)
    for sentence in _sentences(f'{title}. {lead[:1800]}'):
        # Clauses with independent predicates cannot supply one another's
        # firmware versions. Preserve Chinese upgrade-from/to clauses.
        for clause in re.split(r"\b(?:while|whereas|alongside)\b|[,，]\s*and\b", sentence):
            actor = _apple_firmware_actor(clause)
            same_object_continuation = bool(title_owned and actor and re.search(r"firmware|固件", title)
                                            and re.search(r"adapter|适配器|headphones|耳机", clause)
                                            and not re.search(r"\b(?:ios|ipados|macos|tvos|watchos)\b", clause))
            if not re.search(r"firmware|固件", clause) and not same_object_continuation:
                continue
            sentence_device = _device(clause)
            if sentence_device and sentence_device != device:
                continue
            device_receives = bool(sentence_device == device and re.match(
                rf"(?:the\s+)?{device_pattern}\s+(?:receiv\w*|gets?|got)", clause.strip(),
            ))
            if not actor and not device_receives:
                continue
            if not sentence_device and not (title_owned and re.search(r"firmware|固件", title)):
                continue
            if re.search(r"\b(?:previously|last|old)\b|\b(?:not|never)\s+(?:releas\w*|receiv\w*)|"
                         r"^(?:此前|去年)|未推送|尚未推送", clause):
                continue
            version_scope = re.split(r"\b(?:and\s+(?:updates?|releases?)\s+(?:ios|ipados)|(?:ios|ipados)\s+(?:is|version))\b", clause)[0]
            version = _firmware_version(version_scope)
            if version:
                return PrimaryAction(device, f'firmware-release-{version}', 'software_systems')
    return None


def is_primary_firmware_fact(title: str, fact: str) -> bool:
    """Protect the current device/version assertion from topic-word filtering."""
    title, fact = title.lower(), fact.lower()
    if not re.search(r"firmware|固件", fact):
        return False
    device = _device(title)
    if not device or _device(fact) != device:
        return False
    action = owned_primary_action(title, fact, '')
    return bool(action and action.predicate.startswith('firmware-release-'))


def _acquired_company(value: str) -> str:
    for sentence in _sentences(value):
        if not re.search(r"\bapple\b|苹果", sentence):
            continue
        if re.search(r"\bapp(?:lication)?s?\b|应用", sentence):
            # Named application acquisitions have an existing app-specific
            # identity, including passive and award-based descriptions.
            continue
        if re.search(r"\b(?:not|never|denies?|rumou?r\w*|may|might|could)\b|未收购|否认|拟收购|或收购", sentence):
            continue
        match = re.search(
            r"\bapple\s+(?:(?:has|had|today|just|reportedly|already)\s+)*"
            r"(?:acquired|acquires|bought)\s+(?:(?:california-based|startup|company|called|a|the)\s+)*"
            r"(?:assets\s+from\s+)?"
            r"([a-z][a-z0-9-]+)\b|"
            r"苹果(?:公司)?(?:今年|早些时候|已|于|近日|日前|今天|正式|悄悄)*收购(?:了)?(?:一家)?(?:名为)?"
            r"(?:传感技术|脑成像|加州|初创|科技|的|企业|公司)*\s*([a-z][a-z0-9-]+)",
            sentence,
        )
        if match:
            name = match.group(1) or match.group(2)
            if name not in {'a', 'an', 'company', 'startup', 'brain', 'another', 'global', 'rights', 'new', 'working'}:
                return name
    return ''


def owned_primary_action(title: str, lead: str, evidence: str) -> PrimaryAction | None:
    """Extract complete primary actions from normalized headline and evidence."""
    scope = f"{title}. {lead[:1800]}"
    software = 'software_systems'
    hardware = 'hardware_products'
    reviews = re.search(r"\b(?:first|early)\s+reviews\b|首批影评", title)
    work = re.match(r"(.+?)\s+season\s+(\d+)\b", title) or re.search(
        r"apple\s*tv\s*(?:剧集)?\s*([a-z][a-z ]+?)\s*第([一二三四五六七八九\d]+)季", title,
    )
    if reviews and work:
        name, season = work.groups()
        season = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5', '六': '6', '七': '7', '八': '8', '九': '9'}.get(season, season)
        first_assertion = _sentences(lead[:600])[0]
        owns_work = bool(re.search(r"apple\s*tv", title) or (
            re.match(rf"{re.escape(name)}\b", first_assertion)
            and re.search(r"\b(?:on|to)\s+apple\s*tv\b", first_assertion)
            and not re.search(r"\b(?:competes?|unlike|compared)\b", first_assertion)
        ))
        if owns_work:
            return PrimaryAction(f'apple-tv-{_slug(name)}-season-{season}', 'initial-reviews', software)
    if re.search(r"\bcheat\s+sheet\b|\b(?:settings|tips)\s+(?:can|to)\b", title):
        return PrimaryAction(f"editorial-{_slug(title)}", 'guidance-review', software, 'weak')

    if re.search(r"\bapp(?:lication)?\b|应用", title):
        app = _app_object(title)
        # A grammatically Apple-owned release may be planned or already public.
        if app and _apple_app_release(title) and not re.search(
            r"\b(?:not|never|third-party)\b|第三方|未发布|不推出", title,
        ):
            planned = bool(re.search(r"\b(?:plans?|may|will|to\s+introduce|to\s+announce)\b|拟|或将|将推出", title))
            version = re.search(r"(?:\bversion\s*|版本\s*)(\d+(?:\.\d+)+)", title)
            predicate = 'release-plan' if planned else 'release'
            if version:
                predicate += f'-version-{version.group(1)}'
            return PrimaryAction(f"apple-app-{app}", predicate, software)

    if re.search(r"firmware|固件", scope):
        firmware = _firmware_action(title, lead)
        if firmware:
            return firmware

    if (re.search(r"\bacquir\w*|\bacquisition\b|收购|买下", title)
            and re.search(r"\bapple\b|苹果", title)
            and not re.search(r"\b(?:considers?|considering|may|might|could|talks|negotiat\w*)\b|拟|考虑|洽谈|或将", title)):
        company = _acquired_company(scope)
        if company:
            return PrimaryAction(f"apple-acquisition-{company}", 'completed-transaction', hardware)

    if primary_action_domain(title, lead) == 'retail-inventory':
        model = re.search(r"apple\s*watch\s*(?:se|series|ultra)\s*\d+", title)
        if model and re.search(r"\bunavailable\b|\bsold out\b|\bout of stock\b|售罄|缺货", title):
            return PrimaryAction(_slug(model.group()), 'retail-unavailable', hardware)

    if re.search(r"\bproduc(?:ed|tion)\b|产量|生产", title) and not re.search(
        r"\b(?:forecast\w*|predict\w*|expect\w*|target\w*)\b|预测|预估|预计|目标", title,
    ):
        institutions = [name for name, aliases in (*ANALYST_INSTITUTION_ALIASES,
                        ('trendforce', ('trendforce', '集邦')))
                        if any(alias in scope[:450] for alias in aliases)]
        period_pattern = r"(20\d{2})\s*(?:年)?\s*(?:q([1-4])|第([一二三四1-4])(?:季度|季))|\bq([1-4])\s*(20\d{2})"
        title_period = re.search(period_pattern, title)
        continuation = _sentences(lead)[0]
        if not title_period and re.match(r"(?:the\s+)?production\b|产量", continuation):
            continuation_period = re.search(period_pattern, continuation)
            title_quarter = re.search(r"\bq([1-4])\b", title)
            if continuation_period and title_quarter and title_quarter.group(1) == (
                continuation_period.group(2) or continuation_period.group(4)
            ):
                title_period = continuation_period
        if len(institutions) == 1:
            for sentence in _sentences(scope):
                claim = re.search(r"(?:\bapple\b|苹果)[^。;]{0,35}?(?:produc(?:ed|tion)|产量|生产)([^。;]{0,110})", sentence)
                if claim is None:
                    continue
                period = re.search(period_pattern, sentence) or title_period
                product = 'ipad' if re.search(r"\bipads?\b", sentence) else 'iphone' if re.search(
                    r"\b(?:iphones?|smartphones?)\b|手机", sentence + ' ' + title,
                ) else ''
                if not period or not product:
                    continue
                q = period.group(2) or period.group(3) or period.group(4)
                q = {'一': '1', '二': '2', '三': '3', '四': '4'}.get(q, q)
                year = period.group(1) or period.group(5)
                amount = re.search(r"([\d,]+(?:\.\d+)?)\s*(million|万)\s*(?:iphones?|台|部|units)?", claim.group(1))
                if amount:
                    units = int(float(amount.group(1).replace(',', '')) * (1000000 if amount.group(2) == 'million' else 10000))
                    return PrimaryAction(f'{institutions[0]}-{product}-production-{year}-q{q}',
                                         f'actual-units-{units}', hardware)

    if 'carplay' in title:
        model = re.search(r"\b([a-z][a-z0-9-]+)\s+(?:ev|supports?)\b|\b([a-z][a-z0-9-]+)\s*支持", title)
        if model and re.search(r"\b(?:exception|crack|supports?|standard)\b|例外|标配|支持", scope):
            name = model.group(1) or model.group(2)
            if name not in {'apple', 'carplay', 'car', 'vehicle'}:
                year = re.search(r"(20\d{2})\s*(?:models?\b|款)", scope)
                if year:
                    return PrimaryAction(f'carplay-{name}-{year.group(1)}', 'factory-support', software, 'ecosystem')

    if re.search(r"identifiers?\b|标识符", title) and re.search(r"apple|苹果", scope):
        # A catalog-wide registration is distinct from a single-device code leak.
        catalog = re.search(r"\b(?:hardware|product)\s+identifiers\b|硬件标识符", scope)
        backend = re.search(r"\bbackend\b|后台|\badds?\b|新增|show up", scope)
        if catalog and backend:
            batch = re.search(r"(\d+)\s+(?:new\s+)?(?:hardware|product)\s+identifiers|"
                              r"(?:新增|添加)\s*(\d+)\s*个?\s*硬件标识符|"
                              r"(\d+)\s+identifiers", scope)
            if batch:
                count = next(value for value in batch.groups() if value)
                return PrimaryAction('apple-hardware-catalog', f'identifier-registration-count-{count}', hardware)

    biometric = re.search(r"(?<![a-z])touch\s*id(?![a-z])|触控\s*id|触摸\s*id", title)
    if biometric and re.search(r"iphone", title) and re.search(r"\bcode\b|代码|\breferences\b", scope):
        os = re.search(r"(?<![a-z])ios\s*(\d+(?:\.\d+)?)", scope)
        if os:
            product = 'foldable-iphone' if re.search(r"ultra|fold|折叠", title) else 'iphone'
            return PrimaryAction(f'{product}-touch-id-ios-{os.group(1)}', 'code-disclosure', hardware)

    if re.search(r"apple\s*tv", title) and re.search(r"chip|芯片", scope[:650]):
        if re.search(r"\bleak\w*|\bcode\b|\bidentifier\b|代码|曝光|泄露", scope[:900]):
            # The first current chip assertion wins, not historical chips later
            # in the story. Sparse reports without a chip use existing matching.
            for sentence in _sentences(f'{scope}. {evidence[:1400]}'):
                if re.search(r"\b(?:originally|previously|current|last year)\b|原本|此前|现款", sentence):
                    # A contrast may still contain the current assertion first.
                    sentence = re.split(r"\binstead of\b|\brather than\b|而非|取代", sentence)[0]
                    if re.search(r"\b(?:originally|previously|current|last year)\b|原本|此前|现款", sentence):
                        continue
                current = re.search(r"(?<![a-z0-9])a(\d{1,2})(?:\s*(?:/\s*)?pro)?(?![a-z0-9])", sentence)
                if current:
                    return PrimaryAction('apple-tv-chip', f'code-disclosure-a{current.group(1)}', hardware)

    jurisdiction = re.search(r"\buk\b|\bunited kingdom\b|英国", title)
    child = re.search(r"\bchild\w*\b|儿童|未成年人", title)
    law = re.search(r"\b(?:rules|legislation|demands|regulat\w*)\b|法规|立法|要求|拟推动", scope[:900])
    editorial = re.search(r"\b(?:retrospective|critics|criticiz\w*|opinion|history)\b|回顾|批评|评论", title)
    regulator_action = re.search(
        r"\b(?:uk|united kingdom)(?:\s+government)?\s+(?:intends?|plans?|repeats?\s+demands?|"
        r"proposes?|enacts?|demands?)\b|英国(?:政府)?(?:拟|计划|要求|将|进一步)|"
        r"\bapple\s+faces\s+new\s+uk\s+rules\b", scope[:900],
    )
    if jurisdiction and child and law and regulator_action and not editorial and re.search(r"apple|iphone|ios|苹果", scope[:900]):
        # Preserve proposed vs enacted regulatory stages.
        stage = 'enacted' if re.search(r"\b(?:enacts?|passed|takes effect)\b|通过法案|正式生效", title) else 'proposal'
        return PrimaryAction('uk-device-child-safety', f'regulation-{stage}', software)
    return None
