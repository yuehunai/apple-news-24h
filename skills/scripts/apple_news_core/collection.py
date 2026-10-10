"""Collection transport, cache, and detail recall; no final event decisions."""
from __future__ import annotations
import hashlib
import os
import tempfile
from contextlib import contextmanager
import json
import re
import shutil
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from .models import Source, FetchSettings, ReconciliationProfile
from .event_identity import PRODUCT_PATTERNS

def is_navigation_url(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return bool(re.search(r"/(?:tags?|categor(?:y|ies))(?:/|$)", parts.path, re.I)
                or (parts.hostname or '').startswith('forums.'))


def source_article_url_allowed(url: str, source: Source) -> bool:
    """Keep navigation out of article discovery, regardless of link label."""
    if is_navigation_url(url):
        return False
    if source.name != "Apple Newsroom":
        return True
    parts = urllib.parse.urlsplit(url)
    return (
        parts.scheme in {"http", "https"}
        and parts.hostname in source.domains
        and re.fullmatch(
            r"/(?:[a-z]{2,4}(?:-[a-z]{2})?/){0,2}newsroom/\d{4}/(?:0[1-9]|1[0-2])/[^/]+/?",
            parts.path, re.I,
        ) is not None
    )

def build_sources(now_local: datetime) -> list[Source]:
    dates = [now_local.date(), (now_local - timedelta(days=1)).date()]
    macrumors_pages = ["https://www.macrumors.com/", "https://www.macrumors.com/guide/"]
    nine_pages = ["https://9to5mac.com/"]
    for date in dates:
        macrumors_pages.append(
            f"https://www.macrumors.com/{date.year}/{date.month:02d}/{date.day:02d}/"
        )
        nine_pages.append(f"https://9to5mac.com/{date.year}/{date.month:02d}/{date.day:02d}/")

    return [
        Source(
            name="MacRumors",
            default_tz="America/Los_Angeles",
            feeds=["https://feeds.macrumors.com/MacRumors-All"],
            pages=macrumors_pages,
            domains=("macrumors.com", "www.macrumors.com"),
        ),
        Source(
            name="9to5Mac",
            default_tz="America/Los_Angeles",
            feeds=["https://9to5mac.com/feed/"],
            wordpress_posts_apis=[
                "https://9to5mac.com/wp-json/wp/v2/posts?per_page=100&_embed=wp:term&_fields=link,date_gmt,date,title,excerpt,_links.wp:term,_embedded.wp:term"
            ],
            pages=nine_pages,
            domains=("9to5mac.com",),
        ),
        Source(
            name="AppleInsider",
            default_tz="America/New_York",
            feeds=["https://appleinsider.com/rss/news/"],
            pages=["https://appleinsider.com/news"],
            domains=("appleinsider.com",),
        ),
        Source(
            name="The Verge",
            default_tz="America/New_York",
            feeds=[
                "https://www.theverge.com/rss/index.xml",
                "https://www.theverge.com/rss/apple/index.xml",
            ],
            pages=["https://www.theverge.com/apple", "https://www.theverge.com/tech"],
            domains=("theverge.com", "www.theverge.com"),
        ),
        Source(
            name="Apple Newsroom",
            default_tz="America/Los_Angeles",
            feeds=["https://www.apple.com/newsroom/rss-feed.rss"],
            pages=["https://www.apple.com/newsroom/"],
            domains=("apple.com", "www.apple.com"),
        ),
        Source(
            name="IT之家",
            default_tz="Asia/Shanghai",
            feeds=["https://www.ithome.com/rss/"],
            pages=[
                "https://www.ithome.com/",
                "https://www.ithome.com/apple/",
                "https://www.ithome.com/tags/%E8%8B%B9%E6%9E%9C/",
            ],
            domains=("ithome.com", "www.ithome.com"),
        ),
        Source(
            name="爱范儿",
            default_tz="Asia/Shanghai",
            feeds=["https://www.ifanr.com/feed", "http://live.ifanr.com/feed"],
            pages=["https://www.ifanr.com/"],
            domains=("ifanr.com", "www.ifanr.com", "live.ifanr.com"),
        ),
        Source(
            name="快科技",
            default_tz="Asia/Shanghai",
            feeds=["https://rss.mydrivers.com/opml.xml"],
            pages=["https://news.mydrivers.com/"],
            domains=("mydrivers.com", "news.mydrivers.com", "www.mydrivers.com"),
        ),
        Source(
            name="cnBeta",
            default_tz="Asia/Shanghai",
            feeds=["https://www.cnbeta.com.tw/backend.php"],
            pages=["https://www.cnbeta.com.tw/"],
            domains=("cnbeta.com.tw", "www.cnbeta.com.tw"),
        ),
    ]


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


@contextmanager
def run_resource_locks(cache_dir: Path, output_paths: tuple[Path, ...]):
    """Fail immediately on overlapping local run resources; never queue runs."""
    import fcntl
    cache = cache_dir.expanduser().resolve(strict=False)
    targets = {cache}
    for path in output_paths:
        expanded = path.expanduser()
        targets.add(expanded.resolve(strict=False))
        targets.add(expanded.with_name(f".{expanded.name}.tmp").resolve(strict=False))
    lock_root = Path(tempfile.gettempdir()) / f"apple-news-24h-run-locks-{os.getuid()}"
    canonical_locks = lock_root.resolve(strict=False)
    if (cache == canonical_locks or cache in canonical_locks.parents
            or any(canonical_locks == path or canonical_locks in path.parents for path in targets)):
        raise RuntimeError("Run resources overlap the external lock directory")
    if lock_root.is_symlink():
        raise RuntimeError("Refusing a symlinked run lock directory")
    lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Readers of directory ancestors coexist. Clearing that directory requires
    # its exclusive lock, so a nested cache/output cannot be destroyed by it.
    modes = {parent: fcntl.LOCK_SH for target in targets for parent in target.parents}
    modes.update({target: fcntl.LOCK_EX for target in targets})
    held = []
    try:
        for resource, mode in sorted(modes.items(), key=lambda item: str(item[0])):
            name = hashlib.sha256(str(resource).encode("utf-8")).hexdigest() + ".lock"
            descriptor = os.open(lock_root / name, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            handle = os.fdopen(descriptor, "a+b")
            try:
                fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                handle.close()
                raise RuntimeError(f"Run resource is already in use: {resource}") from exc
            except BaseException:
                handle.close()
                raise
            held.append(handle)
        yield
    finally:
        for handle in reversed(held):
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        # Keep inode names stable. Unlinking them would let a second process
        # create a new inode while a first process still owns the old lock.


def prepare_cache_dir(cache_dir: Path, diagnostics: dict[str, Any], *,
    default_cache_dir: Path, marker_filename: str, now: Callable[[], datetime],
) -> Path:
    """Create a dedicated per-run cache directory and clear stale responses safely."""
    cache_dir = cache_dir.expanduser()
    resolved = cache_dir.resolve(strict=False)
    default_resolved = default_cache_dir.resolve(strict=False)
    diagnostics["cache"] = {
        "path": str(cache_dir),
        "resolved_path": str(resolved),
        "cleared_at": now().isoformat(),
        "removed_entries": 0,
        "marker": marker_filename,
    }

    unsafe_targets = {Path("/").resolve(), Path("/tmp").resolve(strict=False)}
    try:
        unsafe_targets.add(Path.home().resolve())
    except Exception:
        pass
    if resolved in unsafe_targets:
        raise RuntimeError(f"Refusing to use unsafe cache directory: {cache_dir}")
    if cache_dir.exists() and cache_dir.is_symlink():
        raise RuntimeError(f"Refusing to clear symlinked cache directory: {cache_dir}")
    if cache_dir.exists() and not cache_dir.is_dir():
        raise RuntimeError(f"Cache path exists but is not a directory: {cache_dir}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    marker_path = cache_dir / marker_filename
    is_default_cache = resolved == default_resolved
    has_marker = marker_path.exists()
    existing_entries = list(cache_dir.iterdir())
    if not is_default_cache and not has_marker and existing_entries:
        raise RuntimeError(
            "Refusing to clear a non-default cache directory without the "
            f"{marker_filename} marker: {cache_dir}"
        )

    removed_entries = 0
    for entry in existing_entries:
        if entry.name == marker_filename:
            continue
        try:
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed_entries += 1
        except FileNotFoundError:
            continue

    marker_path.write_text(
        "This directory is managed by apple-news-24h and is cleared at each run.\n",
        encoding="utf-8",
    )
    diagnostics["cache"]["removed_entries"] = removed_entries
    return cache_dir


def decode_response(raw: bytes, content_type: str | None) -> str:
    charset = None
    if content_type:
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.I)
        if match:
            charset = match.group(1)
    if charset is None:
        head = raw[:2048].decode("ascii", errors="ignore")
        match = re.search(r"charset=['\"]?([A-Za-z0-9._-]+)", head, re.I)
        if match:
            charset = match.group(1)
    for encoding in [charset, "utf-8", "gb18030", "latin-1"]:
        if not encoding:
            continue
        try:
            return raw.decode(encoding, errors="replace")
        except LookupError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_url(
    url: str,
    cache_dir: Path,
    diagnostics: dict[str, Any],
    timeout: float | None = None,
    retries: int | None = None,
    *, settings: FetchSettings, now: Callable[[], datetime],
) -> str | None:
    url = iri_to_uri(url)
    timeout = settings.timeout if timeout is None else timeout
    retries = settings.retries if retries is None else retries
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key(url)}.json"
    last_error = ""

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": settings.user_agent})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read(settings.max_response_bytes)
                text = decode_response(raw, response.headers.get("content-type"))
                payload = {
                    "url": url,
                    "fetched_at": now().isoformat(),
                    "status": getattr(response, "status", None),
                    "text": text,
                }
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
                return text
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))

    diagnostics.setdefault("failed_fetches", []).append({"url": url, "error": last_error})
    return None


def iri_to_uri(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%:@")
    query = urllib.parse.quote(parts.query, safe="=&?/%:@,+")
    fragment = urllib.parse.quote(parts.fragment, safe="=&?/%:@,+")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, fragment))


def direct_apple_report_needs_detail(identity, *, has_lead: bool) -> bool:
    """Title-owned reports survive URL labels and incidental vendor mentions.

    This admits detail verification, not publication. Actual deals, episodes
    and third-party actions do not get this exception from background Apple
    names; the downstream source profile still owns relevance.
    """
    return bool(identity.scope == "apple-direct" and identity.title_products
                and identity.content_form == "news"
                and identity.action_owner in {"apple", "apple-target", "unknown"}
                and (has_lead or identity.title_actions))


def sparse_apple_subject_needs_detail(identity, *, has_lead: bool, event_kind: str, title: str = "") -> bool:
    """An explicit sparse Apple title is collection evidence, not a news verdict."""
    title_text = title.strip()
    if re.search(r"(?:之家|指南|技巧|教程)$|\b(?:guide|tips|cases)\b|"
                 r"\b(?:vs\.?|versus)\b|"
                 r"^(?:how to|hard reset|force restart)\b|"
                 r"[:：]\s*(?:record|apply|reset|restart|enable|disable|customize)\b", title_text, re.I):
        # These phrases describe navigation or instructions, not a missing lead
        # for a particular newly reported action. Other admission evidence is
        # evaluated by the caller; this only withholds the sparse-topic escape.
        return False
    if title and identity is not None and any(
        re.fullmatch(r"(?:(?:the|apple)\s+|苹果\s*)?" + re.escape(alias)
                     + r"(?:\s*(?:\d+(?:\.\d+)*[a-z]?|pro|max|air|mini|ultra|se|plus|studio|duo))*", title.strip(), re.I)
        for product, aliases in PRODUCT_PATTERNS if product in identity.title_products
        for alias in aliases
    ):
        return False
    return bool(not has_lead and identity is not None and identity.scope == "apple-direct"
                and identity.title_products and identity.content_form == "news"
                and identity.action_owner in {"unknown", "apple", "apple-target"}
                and event_kind != "third_party_ecosystem")



def current_apple_role_interview_needs_detail(title: str, lead: str, identity) -> bool:
    """Recall a locally attributed interview without guessing the person's name.

    This establishes a reason to fetch the report, not its final news value.
    A product comparison made by a different company's executive is insufficient.
    """
    if identity is None or not identity.title_products or not lead.strip():
        return False
    opening = re.split(r"[。!?]|(?<=[.])\s+", lead, maxsplit=1)[0]
    role = re.search(
        r"\bApple['’]s\s+(?:(?:new|current|incoming)\s+)?"
        r"(?:CEO|chief executive(?: officer)?|president|(?:senior )?vice president)\s+"
        r"([A-Z][A-Za-z’'-]+(?:\s+[A-Z][A-Za-z’'-]+){1,3})(?=\s+[a-z]|[,，])",
        opening,
    )
    if not role or role.group(1).casefold() not in title.casefold():
        return False
    action = opening[role.end():]
    if re.search(r"\b(?:previously|formerly|last year|never|did not|will|might|could)\b", action, re.I):
        return False
    return bool(re.search(r"\b(?:interview(?:ed)?|sat down|spoke with|talked with)\b", action, re.I))

def detail_recall_weight(profile: ReconciliationProfile, source_tier: str, *, has_lead: bool, title: str = "") -> int:
    """Preserve discovery breadth without granting an editorial outcome.

    A known Apple topic can deserve a detail fetch even when its sparse title,
    index page, or editorial form cannot establish an independent news action.
    Unknown third-party subjects receive no automatic topic bonus.
    """
    identity = profile.identity
    sparse_apple_topic = (
        sparse_apple_subject_needs_detail(identity, has_lead=has_lead, event_kind=profile.event_kind_hint, title=title)
        and not profile.defer_reason and not profile.hard_boundary
        and profile.event_kind_hint != "third_party_ecosystem"
    )
    bound_action = bool(profile.bound_claim and profile.bound_claim.subject
                        and profile.bound_claim.action and profile.bound_claim.object
                        and profile.bound_claim.evidence_spans)
    title_action = bool(identity is not None and identity.title_products and identity.title_actions
                        and identity.scope == "apple-direct" and identity.content_form == "news"
                        and identity.action_owner in {"apple", "apple-target", "unknown"})
    measured_result = bool(identity is not None
                           and "hardware-market-performance" in identity.title_components
                           and any(key.startswith("structured-component-measure:hardware-market-performance:")
                                   for key in profile.event_keys))
    if (source_tier == "strong" and (bound_action or measured_result)
            and not profile.defer_reason and not profile.hard_boundary):
        return 70
    if (source_tier == "strong" and title_action
            and not profile.defer_reason and not profile.hard_boundary):
        # Source-local bindings and concrete headline actions both outrank a
        # retained topic. A generic support flag without an action cannot.
        return 60
    if sparse_apple_topic:
        return 40
    return 40 if source_tier == "strong" else 30 if source_tier == "ecosystem" else 0
