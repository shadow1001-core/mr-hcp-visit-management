from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ErrorDetail:
    field: str
    reason: str
    value: Any | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"field": self.field, "reason": self.reason}
        if self.value is not None:
            result["value"] = str(self.value)
        return result


@dataclass
class BusinessError(Exception):
    code: str
    message: str
    status_code: int
    details: list[ErrorDetail] = field(default_factory=list)
