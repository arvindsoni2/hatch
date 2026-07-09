"""Company watchlist API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WatchSourceType = Literal[
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "generic_careers_page",
    "manual_url_list",
]
WatchStatus = Literal["active", "paused", "error"]
ScanFrequency = Literal["manual", "daily", "weekly"]
RemotePreference = Literal["any", "remote", "hybrid", "onsite"]
ScanStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class CompanyWatchlistCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=256)
    company_website: str | None = None
    careers_url: str = Field(min_length=1, max_length=2048)
    source_type: WatchSourceType
    scan_frequency: ScanFrequency = "manual"
    role_keywords: list[str] | None = None
    location_preferences: list[str] | None = None
    remote_preference: RemotePreference = "any"
    min_match_score: float | None = Field(default=None, ge=0, le=100)

    @field_validator("company_name", "careers_url", "company_website")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class CompanyWatchlistUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=256)
    company_website: str | None = None
    careers_url: str | None = Field(default=None, min_length=1, max_length=2048)
    source_type: WatchSourceType | None = None
    status: WatchStatus | None = None
    scan_frequency: ScanFrequency | None = None
    role_keywords: list[str] | None = None
    location_preferences: list[str] | None = None
    remote_preference: RemotePreference | None = None
    min_match_score: float | None = Field(default=None, ge=0, le=100)


class CompanyWatchlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_name: str
    company_website: str | None = None
    careers_url: str
    source_type: str
    status: str
    scan_frequency: str
    role_keywords: list[str] = Field(default_factory=list)
    location_preferences: list[str] = Field(default_factory=list)
    remote_preference: str
    min_match_score: float | None = None
    last_scanned_at: datetime | None = None
    last_successful_scan_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    last_scan_new_count: int = 0


class CompanyWatchlistList(BaseModel):
    items: list[CompanyWatchlistRead]
    total: int


class WatchlistScanRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    watchlist_item_id: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    source_provider: str
    discovered_count: int
    new_count: int
    duplicate_count: int
    imported_count: int
    error_message: str | None = None
