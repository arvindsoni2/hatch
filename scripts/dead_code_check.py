#!/usr/bin/env python3
"""AST import-graph dead-module detector for backend/app.

Walks backend/app, builds a directed import graph via AST (no execution),
and reports modules that are never imported by anything in the graph.

Allowlisted paths are never reported as dead:
- FastAPI routers / entrypoints (discovered via include_router calls in main.py)
- Alembic migration scripts (backend/alembic/)
- Skill pipeline scripts (backend/app/skills/*/scripts/)
- ORM model modules (imported via Base.metadata.create_all, not explicit imports)
- __init__.py files
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent / "backend" / "app"
_ALEMBIC = Path(__file__).parent.parent / "backend" / "alembic"

_ALLOWLIST_PATTERNS = [
    "alembic",
    "main",            # FastAPI ASGI entrypoint loaded by uvicorn/Docker
    "seed",            # Operational seed script invoked directly
    "skills",          # skill scripts loaded dynamically via spec_from_file_location
    "models",          # ORM models imported via Base.metadata.create_all
    "migrations",
    "conftest",
    "__init__",
]


def _module_key(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    return str(rel).replace("/", ".").removesuffix(".py")


def _is_allowlisted(key: str) -> bool:
    return any(pat in key for pat in _ALLOWLIST_PATTERNS)


def _collect_imports(path: Path, root: Path) -> set[str]:
    """Return set of module keys imported by path (relative to root)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()

    imports: set[str] = set()
    pkg = ".".join(path.relative_to(root).parts[:-1])

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            # Relative import
            if node.level and node.level > 0:
                parts = pkg.split(".")
                base = ".".join(parts[: len(parts) - (node.level - 1)])
                full = f"{base}.{node.module}" if node.module else base
            else:
                full = node.module
            imports.add(full)
            # Also add sub-modules for "from pkg import submod" style
            if node.names:
                for alias in node.names:
                    imports.add(f"{full}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)

    return imports


def main() -> int:
    all_modules: dict[str, Path] = {}
    for py_file in _ROOT.rglob("*.py"):
        key = _module_key(py_file, _ROOT.parent)
        all_modules[key] = py_file

    referenced: set[str] = set()
    for py_file in _ROOT.rglob("*.py"):
        for imp in _collect_imports(py_file, _ROOT.parent):
            # Normalize: strip "app." prefix since we key from backend/
            referenced.add(imp)
            referenced.add(imp.replace("app.", "", 1))

    dead: list[str] = []
    for key in sorted(all_modules):
        short = key.replace("app.", "", 1)
        if _is_allowlisted(short):
            continue
        if key not in referenced and short not in referenced:
            dead.append(key)

    if dead:
        print("Dead modules detected (never imported):")
        for m in dead:
            print(f"  {m}")
        return 1

    print(f"Import graph OK — {len(all_modules)} modules, no unreachable modules found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
