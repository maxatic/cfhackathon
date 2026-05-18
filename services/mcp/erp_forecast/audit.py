"""Audit context manager and event dataclass for MCP tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from .auth import Identity, authorize_tool, validate_bearer_token


@dataclass
class AuditEvent:
    event_id: str
    tool_name: str
    tenant_id: str
    actor: str
    key_id: str
    status: str
    latency_ms: int
    timestamp: str
    error_summary: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "event_id": self.event_id,
            "tool_name": self.tool_name,
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "key_id": self.key_id,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }
        if self.error_summary:
            payload["error_summary"] = self.error_summary
        return payload


class _AuditContext:
    def __init__(
        self,
        store: Any,
        tool_name: str,
        tenant_id: str,
        required_scope: str,
        api_token: str | None,
    ) -> None:
        self.store = store
        self.tool_name = tool_name
        self.tenant_id = tenant_id
        self.required_scope = required_scope
        self.api_token = api_token
        self.started = 0.0
        self.identity: Identity | None = None

    def __enter__(self) -> Identity:
        self.started = perf_counter()
        try:
            self.identity = authorize_tool(self.tenant_id, self.required_scope, self.api_token)
            return self.identity
        except Exception as exc:
            try:
                self.identity = validate_bearer_token(self.api_token)
            except Exception:
                self.identity = None
            self.store._record_audit_event(
                tool_name=self.tool_name,
                tenant_id=self.tenant_id,
                actor=self.identity.subject if self.identity else "unauthorized",
                key_id=self.identity.key_id if self.identity else "none",
                status="error",
                latency_ms=int((perf_counter() - self.started) * 1000),
                error_summary=str(exc)[:180],
            )
            raise

    def __exit__(self, exc_type: object, exc: object, _traceback: object) -> bool:
        latency_ms = int((perf_counter() - self.started) * 1000)
        identity = self.identity
        error_summary = None if exc is None else str(exc)[:180]
        self.store._record_audit_event(
            tool_name=self.tool_name,
            tenant_id=self.tenant_id,
            actor=identity.subject if identity else "unauthorized",
            key_id=identity.key_id if identity else "none",
            status="success" if exc is None else "error",
            latency_ms=latency_ms,
            error_summary=error_summary,
        )
        return False
