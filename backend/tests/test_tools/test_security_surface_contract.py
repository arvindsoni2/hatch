"""Contract: every FastAPI route has exactly one row in the security surface."""
from __future__ import annotations

from pathlib import Path

from fastapi.routing import APIRoute
from starlette.routing import Mount, WebSocketRoute

from app.main import app

ROOT = Path(__file__).resolve().parents[3]
SURFACE = ROOT / "docs" / "architecture" / "SECURITY_SURFACE.md"
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "WS", "MOUNT"}


def _app_routes() -> set[tuple[str, str]]:
    rows: set[tuple[str, str]] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if isinstance(route, APIRoute) or methods:
            for method in methods or ():
                rows.add((method, route.path))
        elif isinstance(route, WebSocketRoute):
            rows.add(("WS", route.path))
        elif isinstance(route, Mount):
            rows.add(("MOUNT", route.path))
    return rows


def _documented_routes() -> set[tuple[str, str]]:
    assert SURFACE.exists(), f"missing {SURFACE}"
    rows: set[tuple[str, str]] = set()
    for line in SURFACE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] in METHODS:
            path = cells[1].strip("`")
            if not path.startswith("/"):
                continue
            assert len(cells) == 8, f"route row must have 8 columns: {line}"
            rows.add((cells[0], path))
    return rows


def test_every_route_has_one_surface_row() -> None:
    app_routes = _app_routes()
    documented = _documented_routes()

    missing = sorted(app_routes - documented)
    extra = sorted(documented - app_routes)
    assert not missing, f"routes missing from SECURITY_SURFACE.md: {missing}"
    assert not extra, f"rows without an app route: {extra}"
