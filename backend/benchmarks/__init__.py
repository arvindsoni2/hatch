"""Local, deterministic CV and cover-letter benchmark harness."""

from .case_loader import CaseValidationError, load_case
from .contracts import BenchmarkCase, ExpectedFacts, ModelSpec

__all__ = [
    "BenchmarkCase",
    "CaseValidationError",
    "ExpectedFacts",
    "ModelSpec",
    "load_case",
]
