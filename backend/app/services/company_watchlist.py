"""Company watchlist service and basic discovery provider."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application
from ..models.company_watchlist import (
    CompanyWatchlistItem,
    DiscoveredRoleFingerprint,
    WatchlistScanRun,
)
from ..models.job import JobPosting
from ..schemas.company_watchlist import (
    CompanyWatchlistCreate,
    CompanyWatchlistRead,
    CompanyWatchlistUpdate,
    WatchlistScanRunRead,
)
from ..services.job_url_importer import normalize_url, preview_url, validate_public_url


@dataclass(frozen=True)
class DiscoveredWatchRole:
    title: str
    company: str
    location: str | None
    url: str
    description: str | None = None
    external_job_id: str | None = None
    posted_at: datetime | None = None


def _now() -> datetime:
    return datetime.utcnow()


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _content_hash(role: DiscoveredWatchRole) -> str | None:
    if not role.description:
        return None
    return hashlib.sha256(role.description.encode("utf-8")).hexdigest()


def _read_item(row: CompanyWatchlistItem, last_scan_new_count: int = 0) -> CompanyWatchlistRead:
    return CompanyWatchlistRead.model_validate(row).model_copy(
        update={
            "role_keywords": row.role_keywords or [],
            "location_preferences": row.location_preferences or [],
            "last_scan_new_count": last_scan_new_count,
        }
    )


def _validate_watch_url(url: str) -> None:
    validate_public_url(url)


async def create_watchlist_item(db: AsyncSession, payload: CompanyWatchlistCreate) -> CompanyWatchlistRead:
    _validate_watch_url(payload.careers_url)
    if payload.company_website:
        _validate_watch_url(payload.company_website)
    row = CompanyWatchlistItem(**payload.model_dump())
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return _read_item(row)


async def list_watchlist_items(db: AsyncSession) -> tuple[list[CompanyWatchlistRead], int]:
    result = await db.execute(select(CompanyWatchlistItem).order_by(CompanyWatchlistItem.created_at.desc()))
    rows = list(result.scalars().all())
    if not rows:
        return [], 0
    latest_counts = await _latest_new_counts(db, [row.id for row in rows])
    return [_read_item(row, latest_counts.get(row.id, 0)) for row in rows], len(rows)


async def _latest_new_counts(db: AsyncSession, item_ids: list[str]) -> dict[str, int]:
    result = await db.execute(
        select(WatchlistScanRun)
        .where(WatchlistScanRun.watchlist_item_id.in_(item_ids))
        .order_by(WatchlistScanRun.completed_at.desc().nullslast())
    )
    counts: dict[str, int] = {}
    for run in result.scalars().all():
        counts.setdefault(run.watchlist_item_id, run.new_count)
    return counts


async def get_watchlist_item(db: AsyncSession, item_id: str) -> CompanyWatchlistItem | None:
    result = await db.execute(select(CompanyWatchlistItem).where(CompanyWatchlistItem.id == item_id))
    return result.scalar_one_or_none()


async def update_watchlist_item(
    db: AsyncSession,
    item_id: str,
    payload: CompanyWatchlistUpdate,
) -> CompanyWatchlistRead | None:
    row = await get_watchlist_item(db, item_id)
    if row is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "careers_url" in data and data["careers_url"]:
        _validate_watch_url(data["careers_url"])
    if "company_website" in data and data["company_website"]:
        _validate_watch_url(data["company_website"])
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = _now()
    await db.flush()
    await db.refresh(row)
    return _read_item(row)


async def delete_watchlist_item(db: AsyncSession, item_id: str) -> bool:
    row = await get_watchlist_item(db, item_id)
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True


async def due_watchlist_items(db: AsyncSession, *, now: datetime | None = None) -> list[CompanyWatchlistItem]:
    current = now or _now()
    daily_cutoff = current - timedelta(days=1)
    weekly_cutoff = current - timedelta(days=7)
    result = await db.execute(
        select(CompanyWatchlistItem).where(
            CompanyWatchlistItem.status == "active",
            or_(
                (CompanyWatchlistItem.scan_frequency == "daily")
                & (
                    (CompanyWatchlistItem.last_scanned_at.is_(None))
                    | (CompanyWatchlistItem.last_scanned_at <= daily_cutoff)
                ),
                (CompanyWatchlistItem.scan_frequency == "weekly")
                & (
                    (CompanyWatchlistItem.last_scanned_at.is_(None))
                    | (CompanyWatchlistItem.last_scanned_at <= weekly_cutoff)
                ),
            ),
        )
    )
    return list(result.scalars().all())


async def run_due_watchlist_scans(db: AsyncSession) -> dict[str, int]:
    due = await due_watchlist_items(db)
    completed = 0
    failed = 0
    for item in due:
        run = await scan_watchlist_item(db, item.id)
        if run.status == "completed":
            completed += 1
        else:
            failed += 1
    return {"due": len(due), "completed": completed, "failed": failed}


async def discover_roles_for_item(item: CompanyWatchlistItem) -> list[DiscoveredWatchRole]:
    """Discover roles from an explicitly configured user URL using the basic provider."""
    validate_public_url(item.careers_url)
    headers = {"User-Agent": "Hatch-Watchlist/1.0"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5), follow_redirects=True) as client:
        response = await client.get(item.careers_url, headers=headers)
        response.raise_for_status()
        text = response.text

    links = _extract_role_links(text, item.careers_url)
    if not links:
        links = [item.careers_url]

    roles: list[DiscoveredWatchRole] = []
    for url in links[:20]:
        try:
            preview = await preview_url(url)
        except Exception:
            continue
        title = str(preview.get("title") or "").strip()
        if not title:
            continue
        roles.append(
            DiscoveredWatchRole(
                title=title,
                company=str(preview.get("company") or item.company_name).strip(),
                location=str(preview.get("location") or "").strip() or None,
                url=str(preview.get("final_url") or preview.get("normalized_url") or url),
                description=str(preview.get("description") or "").strip() or None,
                external_job_id=_external_id(url),
            )
        )
    return roles


def _extract_role_links(html_text: str, base_url: str) -> list[str]:
    links: list[str] = []
    for raw in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html_text, re.I | re.S):
        href, label = raw
        target = normalize_url(urljoin(base_url, html.unescape(href)))
        text = html.unescape(re.sub(r"<[^>]+>", " ", label)).lower()
        url_lower = target.lower()
        if any(token in url_lower or token in text for token in ("job", "role", "career", "opening", "position")):
            if target not in links:
                links.append(target)
    return links


def _external_id(url: str) -> str | None:
    path = normalize_url(url).rstrip("/").rsplit("/", 1)[-1]
    return path or None


async def scan_watchlist_item(db: AsyncSession, item_id: str) -> WatchlistScanRunRead:
    item = await get_watchlist_item(db, item_id)
    if item is None:
        raise ValueError("watchlist item not found")

    started = _now()
    run = WatchlistScanRun(
        watchlist_item_id=item.id,
        status="running",
        started_at=started,
        source_provider="builtin_basic",
    )
    db.add(run)
    await db.flush()

    try:
        roles = await discover_roles_for_item(item)
        imported = 0
        duplicate = 0
        for role in roles:
            if await _is_duplicate(db, role):
                duplicate += 1
                await _touch_fingerprint(db, role)
                continue
            try:
                async with db.begin_nested():
                    job = JobPosting(
                        title=role.title,
                        company=role.company or item.company_name,
                        location=role.location,
                        description=role.description,
                        url=normalize_url(role.url),
                        source="watched_company",
                        posted_at=role.posted_at,
                        scraped_at=_now(),
                        match_score=item.min_match_score,
                    )
                    db.add(job)
                    await db.flush()
            except IntegrityError:
                duplicate += 1
                continue
            db.add(Application(job_id=job.id, status="discovered", priority="normal"))
            await _touch_fingerprint(db, role)
            imported += 1

        completed = _now()
        run.status = "completed"
        run.completed_at = completed
        run.discovered_count = len(roles)
        run.new_count = imported
        run.duplicate_count = duplicate
        run.imported_count = imported
        item.last_scanned_at = completed
        item.last_successful_scan_at = completed
        item.last_error = None
        item.status = "active"
        item.updated_at = completed
    except Exception as exc:
        completed = _now()
        run.status = "failed"
        run.completed_at = completed
        run.error_message = str(exc)
        item.last_scanned_at = completed
        item.last_error = str(exc)
        item.status = "error"
        item.updated_at = completed

    await db.flush()
    await db.refresh(run)
    return WatchlistScanRunRead.model_validate(run)


async def _is_duplicate(db: AsyncSession, role: DiscoveredWatchRole) -> bool:
    url = normalize_url(role.url)
    content_hash = _content_hash(role)
    normalized_company = _norm(role.company)
    normalized_title = _norm(role.title)
    normalized_location = _norm(role.location)

    job_result = await db.execute(select(JobPosting.id).where(JobPosting.url == url))
    if job_result.scalar_one_or_none() is not None:
        return True

    clauses = [DiscoveredRoleFingerprint.source_url == url]
    if role.external_job_id:
        clauses.append(
            (DiscoveredRoleFingerprint.normalized_company == normalized_company)
            & (DiscoveredRoleFingerprint.external_job_id == role.external_job_id)
        )
    if normalized_company and normalized_title:
        clauses.append(
            (DiscoveredRoleFingerprint.normalized_company == normalized_company)
            & (DiscoveredRoleFingerprint.normalized_title == normalized_title)
            & (DiscoveredRoleFingerprint.normalized_location == normalized_location)
        )
    if content_hash:
        clauses.append(DiscoveredRoleFingerprint.content_hash == content_hash)

    fp_result = await db.execute(select(func.count()).select_from(DiscoveredRoleFingerprint).where(or_(*clauses)))
    return bool(fp_result.scalar_one())


async def _touch_fingerprint(db: AsyncSession, role: DiscoveredWatchRole) -> None:
    url = normalize_url(role.url)
    result = await db.execute(select(DiscoveredRoleFingerprint).where(DiscoveredRoleFingerprint.source_url == url))
    row = result.scalar_one_or_none()
    now = _now()
    if row is None:
        db.add(
            DiscoveredRoleFingerprint(
                source_url=url,
                normalized_company=_norm(role.company),
                normalized_title=_norm(role.title),
                normalized_location=_norm(role.location),
                external_job_id=role.external_job_id,
                content_hash=_content_hash(role),
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    else:
        row.last_seen_at = now
