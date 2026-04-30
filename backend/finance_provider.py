"""Static mortgage presets (Phase 6 provider abstraction — default implementation)."""

from __future__ import annotations

from typing import Any

# Mirrors `frontend/app.js` MORTGAGE_PRESETS for API consumers / future lender adapter swap.
MORTGAGE_PRESETS: dict[str, dict[str, Any]] = {
    "30fixed": {"label": "30-year fixed", "months": 360, "defaultAprPercent": 6.5},
    "15fixed": {"label": "15-year fixed", "months": 180, "defaultAprPercent": 5.875},
    "71arm": {"label": "7/1 ARM", "months": 360, "defaultAprPercent": 6.125},
    "51arm": {"label": "5/1 ARM", "months": 360, "defaultAprPercent": 6.0},
    "custom": {"label": "Custom term", "months": None, "defaultAprPercent": 6.5},
}


def mortgage_presets_payload() -> dict[str, Any]:
    return {"schema_version": 1, "presets": MORTGAGE_PRESETS}


class StaticFinanceRateProvider:
    """Default ``FinanceRateProvider`` until a partner bank API adapter exists."""

    def presets(self) -> dict[str, Any]:
        return dict(MORTGAGE_PRESETS)
