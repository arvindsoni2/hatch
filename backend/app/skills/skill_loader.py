"""SkillRegistry and SkillLoader — progressive disclosure for agent skills."""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class SkillContract:
    """Machine-readable execution boundary for a registered skill."""

    skill_id: str
    skill_version: str
    input_schema: str
    output_schema: str
    preconditions: tuple[str, ...]
    validators: tuple[str, ...]
    allowed_repair_actions: tuple[str, ...]
    maximum_attempts: int
    safe_failure_state: str


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split YAML frontmatter from markdown body.

    Returns (metadata_dict, body_text). Metadata keys are the raw YAML keys;
    only simple key: value pairs (no nested YAML) are parsed.
    """
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break

    if end is None:
        return {}, text

    fm_lines = lines[1:end]
    body = "\n".join(lines[end + 1:]).strip()

    meta: dict[str, str] = {}
    for line in fm_lines:
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()

    return meta, body


class SkillRegistry:
    """Discovers skill folders under a given directory."""

    def __init__(self, skills_dir: Path) -> None:
        self._dir = Path(skills_dir)

    def list(self) -> list[str]:
        """Return sorted list of skill names (folder names containing SKILL.md)."""
        if not self._dir.exists():
            return []
        names = [
            p.name
            for p in self._dir.iterdir()
            if p.is_dir() and (p / "SKILL.md").exists()
        ]
        return sorted(names)

    def has(self, name: str) -> bool:
        """Return True if the named skill folder with SKILL.md exists."""
        return (self._dir / name / "SKILL.md").exists()

    def skill_dir(self, name: str) -> Path:
        """Return the Path to the skill folder (does not check existence)."""
        return self._dir / name


class SkillLoader:
    """Loads skill content progressively: metadata first, instructions and resources on demand."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def metadata(self, name: str) -> dict[str, str]:
        """Return lightweight metadata for a skill (frontmatter only).

        For unknown skills returns a fallback dict with empty strings rather
        than raising, so agents can safely probe skill availability.
        """
        skill_md = self._registry.skill_dir(name) / "SKILL.md"
        if not skill_md.exists():
            return {"name": name, "description": "", "when_to_use": ""}

        text = skill_md.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        return {
            "name": fm.get("name", name),
            "description": fm.get("description", ""),
            "when_to_use": fm.get("when_to_use", ""),
        }

    def instructions(self, name: str) -> str:
        """Return the full SKILL.md body (without frontmatter) for context injection.

        Returns '' for unknown skills.
        """
        skill_md = self._registry.skill_dir(name) / "SKILL.md"
        if not skill_md.exists():
            return ""
        text = skill_md.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    def contract(self, name: str) -> SkillContract | None:
        """Load and validate the optional machine-readable skill contract."""
        if not self._registry.has(name):
            return None
        path = self._registry.skill_dir(name) / "contract.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Invalid skill contract JSON: {path}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"Skill contract must be a JSON object: {path}")

        scalar_fields = (
            "skill_id",
            "skill_version",
            "input_schema",
            "output_schema",
            "safe_failure_state",
        )
        list_fields = (
            "preconditions",
            "validators",
            "allowed_repair_actions",
        )
        for field in scalar_fields:
            if not isinstance(raw.get(field), str) or not raw[field]:
                raise ValueError(f"Skill contract field {field!r} must be a non-empty string")
        for field in list_fields:
            value = raw.get(field)
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(item, str) and item for item in value)
            ):
                raise ValueError(f"Skill contract field {field!r} must be a non-empty string list")
        maximum_attempts = raw.get("maximum_attempts")
        if not isinstance(maximum_attempts, int) or maximum_attempts < 1:
            raise ValueError("Skill contract maximum_attempts must be a positive integer")
        if raw["skill_id"] != name:
            raise ValueError(
                f"Skill contract ID {raw['skill_id']!r} does not match folder {name!r}"
            )

        return SkillContract(
            skill_id=raw["skill_id"],
            skill_version=raw["skill_version"],
            input_schema=raw["input_schema"],
            output_schema=raw["output_schema"],
            preconditions=tuple(raw["preconditions"]),
            validators=tuple(raw["validators"]),
            allowed_repair_actions=tuple(raw["allowed_repair_actions"]),
            maximum_attempts=maximum_attempts,
            safe_failure_state=raw["safe_failure_state"],
        )

    def resource(self, name: str, filename: str) -> str:
        """Return the raw string content of a resources/ file for the named skill.

        Raises:
            KeyError: if the skill does not exist.
            FileNotFoundError: if the resource file does not exist within the skill.
        """
        if not self._registry.has(name):
            raise KeyError(f"Unknown skill: {name!r}")
        path = self._registry.skill_dir(name) / "resources" / filename
        if not path.exists():
            raise FileNotFoundError(f"Resource not found: {path}")
        return path.read_text(encoding="utf-8")

    def script(self, name: str, filename: str) -> Callable[..., Any]:
        """Load a scripts/ file for the named skill and return its main callable.

        The callable is the function whose name matches the script filename stem
        (e.g. ``ats_lint.py`` → ``ats_lint``).

        Raises:
            FileNotFoundError: if the script file does not exist.
        """
        path = self._registry.skill_dir(name) / "scripts" / filename
        if not path.exists():
            raise FileNotFoundError(f"Script not found: {path}")

        module_name = f"_skill_{name}_{path.stem}".replace("-", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load script: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        fn_name = path.stem
        fn = getattr(module, fn_name, None)
        if fn is None:
            raise AttributeError(
                f"Script {filename!r} must define a function named {fn_name!r}"
            )
        return fn
