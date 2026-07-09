"""Canonical app-lock password policy."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = 12
    max_length: int = 128
    require_letter: bool = True
    require_number: bool = True
    require_symbol: bool = True
    reject_edge_whitespace: bool = True

    def public(self) -> dict[str, int | bool]:
        return {
            "min_length": self.min_length,
            "max_length": self.max_length,
            "require_letter": self.require_letter,
            "require_number": self.require_number,
            "require_symbol": self.require_symbol,
            "reject_edge_whitespace": self.reject_edge_whitespace,
        }

    def violations(self, password: str) -> list[str]:
        violations: list[str] = []
        if len(password) < self.min_length:
            violations.append(f"Use at least {self.min_length} characters.")
        if len(password) > self.max_length:
            violations.append(f"Use no more than {self.max_length} characters.")
        if self.require_letter and not re.search(r"[A-Za-z]", password):
            violations.append("Include at least one letter.")
        if self.require_number and not re.search(r"\d", password):
            violations.append("Include at least one number.")
        if self.require_symbol and not re.search(r"[^A-Za-z0-9\s]", password):
            violations.append("Include at least one symbol or punctuation mark.")
        if self.reject_edge_whitespace and password != password.strip():
            violations.append("Remove spaces from the beginning and end.")
        return violations


APP_LOCK_PASSWORD_POLICY = PasswordPolicy()


def validate_new_password(password: str) -> None:
    violations = APP_LOCK_PASSWORD_POLICY.violations(password)
    if violations:
        raise ValueError(violations[0])
