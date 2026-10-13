"""AI summary provider placeholder.

Phase 6C intentionally does not bind to any paid AI API. This provider is
reserved for future use.
"""

from __future__ import annotations


class AISummaryProvider:
    """Placeholder for an optional AI-backed summary provider."""

    def generate(self, description: str, content: str, target_language: str) -> str:
        raise NotImplementedError("AI summary provider is not implemented in Phase 6C.")
