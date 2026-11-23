"""RED contract for P6: dependency direction (spec §5.1, §5.3, AC36).

Written by Claude Code before implementation (plan §1.5). Static AST scan of
backend/app: only Phase 2 files (spec §5.2), the composition root and the runtime
binding registries may import a ``coach_readiness`` module; existing domains reach
Phase 2 only through the neutral ``services/source_events.py`` seam.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

# Spec §5.2 Phase 2 files (plus the P6 context binding), main.py (composition
# root), models/__init__.py (table registration) and the runtime_bindings
# registries that P6 extends.
ALLOWED = {
    "main.py",
    "models/__init__.py",
    "models/coach_readiness.py",
    "repositories/coach_readiness_repository.py",
    "schemas/coach_readiness.py",
    "routers/coach_readiness.py",
    "runtime_bindings/tasks/coach_readiness.py",
    "runtime_bindings/tasks/__init__.py",
    "runtime_bindings/context/coach_readiness.py",
    "runtime_bindings/context/__init__.py",
    "runtime_bindings/capabilities/registry.py",
}
ALLOWED_PREFIX = "services/coach_readiness/"

# §5.3 call sites: existing domains that must report changes through source_events.
CALL_SITES = (
    "repositories/conversational_session_repository.py",
    "repositories/story_repository.py",
    "services/question_bank.py",
)


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(APP.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(path: Path) -> set[str]:
    """Absolute dotted names of every module (and imported name) in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _module_name(path)
    if path.name != "__init__.py":
        package = package.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".")
                base_parts = base_parts[: len(base_parts) - (node.level - 1)]
                base = ".".join(base_parts)
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            # importlib.import_module("app.services.coach_readiness...") / __import__
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"import_module", "__import__"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value)
    return found


def _is_phase2(module: str) -> bool:
    return "coach_readiness" in module.split(".")


def test_existing_domains_do_not_import_coach_readiness() -> None:
    assert (APP / "services" / "source_events.py").is_file(), "missing services/source_events.py"

    violations = []
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP).as_posix()
        if relative in ALLOWED or relative.startswith(ALLOWED_PREFIX):
            continue
        offending = sorted(m for m in _imported_modules(path) if _is_phase2(m))
        if offending:
            violations.append(f"{relative}: {', '.join(offending)}")
    assert violations == [], "existing modules import coach_readiness:\n" + "\n".join(violations)

    # The neutral seam itself holds no Phase 2 dependency.
    seam = _imported_modules(APP / "services" / "source_events.py")
    assert not any(_is_phase2(module) for module in seam)

    # Each §5.3 call site reaches Phase 2 only through source_events (K7: the
    # seams must not silently disappear).
    for relative in CALL_SITES:
        imported = _imported_modules(APP / relative)
        assert any(
            module == "app.services.source_events" or module.startswith("app.services.source_events.")
            for module in imported
        ), f"{relative} does not use app.services.source_events"
