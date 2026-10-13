"""Preflight result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TECHNICAL_CHECK_NAMES = {
    "SKILL.md",
    "compatibility",
    "frontmatter",
    "target-agent",
    "capabilities",
    "skill-format",
    "compatibility-notes",
    "skill-content-compatibility",
    "allowed-tools",
}


@dataclass
class CheckResult:
    """Result of a single Preflight check."""

    name: str
    status: str  # pass | warn | block
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": dict(self.details),
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"CheckResult(name={self.name!r}, status={self.status!r})"


@dataclass
class PreflightResult:
    """Aggregated result of a Preflight run."""

    status: str = "pass"  # pass | warn | block
    checks: list[CheckResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def technical_compatibility(self) -> dict[str, Any]:
        """Summarize Harness/format compatibility separately from sync safety."""
        checks = [
            check
            for check in self.checks
            if check.name in TECHNICAL_CHECK_NAMES or check.name.startswith("runtime-")
        ]
        if not checks:
            status = "unknown"
        elif any(check.status == "block" for check in checks):
            status = "incompatible"
        elif any(check.status == "warn" for check in checks):
            status = "review"
        else:
            status = "compatible"
        notes = list(dict.fromkeys(
            check.message for check in checks if check.status in {"warn", "block"} and check.message
        ))
        return {"status": status, "notes": notes}

    @classmethod
    def from_checks(cls, checks: list[CheckResult]) -> "PreflightResult":
        status = "pass"
        warnings: list[str] = []
        errors: list[str] = []
        for check in checks:
            if check.status == "block":
                status = "block"
                errors.append(check.message or check.name)
            elif check.status == "warn" and status != "block":
                status = "warn"
                warnings.append(check.message or check.name)
        summary = {
            "pass": "All checks passed",
            "warn": "Checks completed with warnings",
            "block": "Preflight blocked",
        }[status]
        return cls(
            status=status,
            checks=checks,
            warnings=warnings,
            errors=errors,
            summary=summary,
        )

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "summary": self.summary,
            "checks": [c.to_dict() for c in self.checks],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "technicalCompatibility": self.technical_compatibility,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"PreflightResult(status={self.status!r}, checks={len(self.checks)})"
