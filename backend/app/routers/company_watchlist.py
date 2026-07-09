"""Company watchlist endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.company_watchlist import (
    CompanyWatchlistCreate,
    CompanyWatchlistList,
    CompanyWatchlistRead,
    CompanyWatchlistUpdate,
    WatchlistScanRunRead,
)
from ..services.company_watchlist import (
    create_watchlist_item,
    delete_watchlist_item,
    list_watchlist_items,
    scan_watchlist_item,
    update_watchlist_item,
)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("/companies", response_model=CompanyWatchlistList)
async def list_companies(db: AsyncSession = Depends(get_db)) -> CompanyWatchlistList:
    items, total = await list_watchlist_items(db)
    return CompanyWatchlistList(items=items, total=total)


@router.post("/companies", response_model=CompanyWatchlistRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyWatchlistCreate,
    db: AsyncSession = Depends(get_db),
) -> CompanyWatchlistRead:
    try:
        return await create_watchlist_item(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/companies/{item_id}", response_model=CompanyWatchlistRead)
async def update_company(
    item_id: str,
    payload: CompanyWatchlistUpdate,
    db: AsyncSession = Depends(get_db),
) -> CompanyWatchlistRead:
    try:
        item = await update_watchlist_item(db, item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    return item


@router.delete("/companies/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(item_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    deleted = await delete_watchlist_item(db, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/companies/{item_id}/scan", response_model=WatchlistScanRunRead)
async def scan_company(item_id: str, db: AsyncSession = Depends(get_db)) -> WatchlistScanRunRead:
    try:
        return await scan_watchlist_item(db, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
