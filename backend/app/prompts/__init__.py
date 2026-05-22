"""Jinja2 prompt template renderer for the Tailor pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent)),
    autoescape=select_autoescape(enabled_extensions=(), default_for_string=False),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_prompt(template_name: str, **variables: Any) -> str:
    """Render a Jinja2 prompt template with the given variables.

    Args:
        template_name: Filename of the .j2 template (e.g. 'jd_analysis.j2').
        **variables: Template variables injected at render time.

    Returns:
        Rendered prompt string.
    """
    template = _env.get_template(template_name)
    return template.render(**variables)
