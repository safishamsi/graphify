"""Detector policy loading and enablement rules."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from depos.analysis.schemas import Detector


class DetectorPolicy(BaseModel):
    enabled: set[str] = Field(default_factory=set)
    disabled: set[str] = Field(default_factory=set)
    severity_overrides: dict[str, str] = Field(default_factory=dict)

    def is_enabled(self, spec: Detector) -> bool:
        if spec.name in self.disabled:
            return False
        if self.enabled:
            return spec.name in self.enabled
        return spec.enabled_by_default

    def severity_for(self, spec: Detector) -> str:
        return self.severity_overrides.get(spec.name, spec.severity_default)


def load_policy(raw: Any | None) -> DetectorPolicy:
    if raw is None:
        return DetectorPolicy()
    if isinstance(raw, DetectorPolicy):
        return raw
    if isinstance(raw, dict):
        return DetectorPolicy(
            enabled=set(str(v) for v in raw.get("enabled", []) if str(v).strip()),
            disabled=set(str(v) for v in raw.get("disabled", []) if str(v).strip()),
            severity_overrides={str(k): str(v) for k, v in dict(raw.get("severity_overrides", {})).items()},
        )
    return DetectorPolicy()


__all__ = ["DetectorPolicy", "load_policy"]
