"""In-memory orchestrator: audit events and latest prediction cache.

Holds runtime state required by `_AuditContext` and by the
`list_audit_events` tool plus `swift://prediction/latest` resource.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .audit import AuditEvent

_MAX_AUDIT_EVENTS = 1000


class _Store:
    """Single-process in-memory state container."""

    def __init__(self) -> None:
        self._audit_events: list[AuditEvent] = []
        self._latest_prediction: dict[str, Any] | None = None

    def _record_audit_event(
        self,
        tool_name: str,
        tenant_id: str,
        actor: str,
        key_id: str,
        status: str,
        latency_ms: int,
        error_summary: str | None = None,
    ) -> None:
        event = AuditEvent(
            event_id=str(uuid4()),
            tool_name=tool_name,
            tenant_id=tenant_id,
            actor=actor,
            key_id=key_id,
            status=status,
            latency_ms=latency_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            error_summary=error_summary,
        )
        self._audit_events.append(event)
        if len(self._audit_events) > _MAX_AUDIT_EVENTS:
            self._audit_events = self._audit_events[-_MAX_AUDIT_EVENTS:]

    def list_audit_events(self, limit: int = 100) -> list[dict[str, object]]:
        clamped = max(1, min(int(limit), _MAX_AUDIT_EVENTS))
        return [event.to_dict() for event in self._audit_events[-clamped:]]

    def record_latest_prediction(self, tool_name: str, payload: dict[str, Any]) -> None:
        self._latest_prediction = {
            "tool_name": tool_name,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

    def get_latest_prediction(self) -> dict[str, Any] | None:
        return self._latest_prediction


STORE = _Store()
