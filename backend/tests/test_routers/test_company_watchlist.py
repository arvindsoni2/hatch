from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.job import JobPosting
from app.services.company_watchlist import DiscoveredWatchRole


def _watchlist_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "company_name": "Example Cloud",
        "company_website": "https://example.com",
        "careers_url": "https://example.com/careers",
        "source_type": "generic_careers_page",
        "scan_frequency": "daily",
        "role_keywords": ["architect", "delivery"],
        "location_preferences": ["London", "Remote"],
        "remote_preference": "any",
        "min_match_score": 65,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_create_list_pause_and_delete_watchlist_item(client: AsyncClient) -> None:
    create_response = await client.post("/api/watchlist/companies", json=_watchlist_payload())

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["company_name"] == "Example Cloud"
    assert created["status"] == "active"
    assert created["source_type"] == "generic_careers_page"

    list_response = await client.get("/api/watchlist/companies")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == created["id"]

    pause_response = await client.patch(
        f"/api/watchlist/companies/{created['id']}",
        json={"status": "paused"},
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == "paused"

    delete_response = await client.delete(f"/api/watchlist/companies/{created['id']}")
    assert delete_response.status_code == 204
    assert (await client.get("/api/watchlist/companies")).json()["total"] == 0


@pytest.mark.asyncio
async def test_manual_scan_imports_deduped_roles_as_discovered_applications(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_response = await client.post("/api/watchlist/companies", json=_watchlist_payload())
    item_id = create_response.json()["id"]
    existing = JobPosting(
        title="Cloud Architect",
        company="Example Cloud",
        location="Remote",
        url="https://example.com/jobs/existing",
        source="watched_company",
    )
    db_session.add(existing)
    await db_session.commit()

    async def fake_discover(*_: object, **__: object) -> list[DiscoveredWatchRole]:
        return [
            DiscoveredWatchRole(
                title="Cloud Architect",
                company="Example Cloud",
                location="Remote",
                url="https://example.com/jobs/existing",
                description="Duplicate role",
                external_job_id="existing",
            ),
            DiscoveredWatchRole(
                title="Delivery Lead",
                company="Example Cloud",
                location="London",
                url="https://example.com/jobs/new-delivery-lead",
                description="Lead delivery across cloud programmes.",
                external_job_id="new-delivery-lead",
            ),
        ]

    monkeypatch.setattr("app.services.company_watchlist.discover_roles_for_item", fake_discover)

    response = await client.post(f"/api/watchlist/companies/{item_id}/scan")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["discovered_count"] == 2
    assert body["new_count"] == 1
    assert body["duplicate_count"] == 1
    assert body["imported_count"] == 1

    jobs = await db_session.execute(
        select(JobPosting).where(JobPosting.url == "https://example.com/jobs/new-delivery-lead")
    )
    imported = jobs.scalar_one()
    assert imported.source == "watched_company"
    assert imported.company == "Example Cloud"

    app_count = await db_session.scalar(
        select(func.count()).select_from(Application).where(Application.job_id == imported.id)
    )
    assert app_count == 1


@pytest.mark.asyncio
async def test_due_watchlist_items_include_daily_and_weekly_only_when_due(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    daily_due = await client.post("/api/watchlist/companies", json=_watchlist_payload(company_name="Daily Due"))
    weekly_due = await client.post("/api/watchlist/companies", json=_watchlist_payload(company_name="Weekly Due", scan_frequency="weekly"))
    weekly_recent = await client.post("/api/watchlist/companies", json=_watchlist_payload(company_name="Weekly Recent", scan_frequency="weekly"))
    manual = await client.post("/api/watchlist/companies", json=_watchlist_payload(company_name="Manual", scan_frequency="manual"))

    from app.models.company_watchlist import CompanyWatchlistItem
    from app.services.company_watchlist import due_watchlist_items

    now = datetime.utcnow()
    rows = await db_session.execute(select(CompanyWatchlistItem))
    by_id = {row.id: row for row in rows.scalars().all()}
    by_id[daily_due.json()["id"]].last_scanned_at = now - timedelta(days=1, minutes=5)
    by_id[weekly_due.json()["id"]].last_scanned_at = now - timedelta(days=7, minutes=5)
    by_id[weekly_recent.json()["id"]].last_scanned_at = now - timedelta(days=2)
    by_id[manual.json()["id"]].last_scanned_at = None
    await db_session.commit()

    due = await due_watchlist_items(db_session, now=now)

    due_names = {item.company_name for item in due}
    assert due_names == {"Daily Due", "Weekly Due"}
