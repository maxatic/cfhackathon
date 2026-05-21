"""Input and output schemas for the six locked MCP tools.

Schemas mirror the contracts in `comms/handoffs.md` exactly. Used by `server.py`
to keep the public tool surface stable across Lane A wiring and Lane C
implementations.
"""

from __future__ import annotations

from typing import Any, TypedDict


# Hardcoded single demo tenant per AGENTS.md.
DEMO_TENANT_ID = "nexus_lab_solutions"

# Beam-search horizon bounds for predict_scenarios and forecast_plan.
# Beam decoding runs `beam_width * horizon` model steps. Long horizons on CPU
# breach MCP client read timeouts (default 60s for stdio, lower for HTTP),
# so callers may pass any value but the server clamps it to BEAM_HORIZON_MAX.
BEAM_HORIZON_DEFAULT = 6
BEAM_HORIZON_MAX = 12

# Scope each locked tool requires from `auth.py` API keys.
SCOPE_FOR_TOOL: dict[str, str] = {
    "predict_next_basket": "forecast",
    "predict_scenarios": "forecast",
    "forecast_plan": "forecast",
    "personalize_client": "forecast",
    "anonymize_and_tokenize_orders": "anonymize",
    "list_clients": "models",
    "list_audit_events": "audit",
}


class DecoderConfig(TypedDict, total=False):
    strategy: str
    top_k: int
    temperature: float
    max_generate: int
    seed: int
    beam_width: int
    horizon: int


class PredictNextBasketInput(TypedDict, total=False):
    client_id: str
    start_sequence: list[str] | None
    max_generate: int
    top_k: int
    temperature: float
    seed: int | None
    api_token: str | None


class PredictNextBasketOutput(TypedDict):
    client_id: str
    start_sequence: list[str]
    generated_tokens: list[str]
    generated_times: list[int]
    model_version: str
    decoder_config: DecoderConfig


class PredictScenariosInput(TypedDict, total=False):
    client_id: str
    start_sequence: list[str] | None
    beam_width: int
    horizon: int
    temperature: float
    api_token: str | None


class ScenarioTrajectory(TypedDict):
    rank: int
    joint_log_prob: float
    tokens: list[str]
    time_deltas: list[int]


class PredictScenariosOutput(TypedDict):
    client_id: str
    scenarios: list[ScenarioTrajectory]
    model_version: str
    decoder_config: DecoderConfig


class ForecastPlanInput(TypedDict, total=False):
    client_id: str
    objective_text: str
    horizon_hint: int | None
    api_token: str | None


class ForecastPlanOutput(TypedDict):
    client_id: str
    chosen_strategy: str
    rationale: str
    payload: dict[str, Any]
    model_version: str


class PersonalizeClientInput(TypedDict, total=False):
    client_id: str
    additional_tokens: list[str]
    start_sequence: list[str] | None
    max_generate: int
    top_k: int
    temperature: float
    seed: int | None
    api_token: str | None


class PersonalizeClientOutput(TypedDict):
    session_id: str
    client_id: str
    additional_tokens: list[str]
    prediction: PredictNextBasketOutput


class AuditReport(TypedDict):
    row_count: int
    fields_hashed: list[str]
    fields_scrubbed: list[str]
    detected_sensitive_fields: list[str]
    k_anonymity_proxy: int
    privacy_notes: list[str]


class TokenizedRow(TypedDict, total=False):
    row_id: str
    source_label: str
    token: str
    time_delta: int


class AnonymizeAndTokenizeInput(TypedDict, total=False):
    raw_rows: list[dict[str, Any]]
    client_id: str
    api_token: str | None


class AnonymizeAndTokenizeOutput(TypedDict):
    client_id: str
    tokenized: list[str]
    time_deltas: list[int]
    audit_report: AuditReport
    rows: list[TokenizedRow]


class ListClientsInput(TypedDict, total=False):
    api_token: str | None


class ListClientsOutput(TypedDict):
    clients: list[str]
    count: int
    model_version: str


class ListAuditEventsInput(TypedDict, total=False):
    limit: int
    api_token: str | None


class AuditEventOut(TypedDict, total=False):
    event_id: str
    tool_name: str
    tenant_id: str
    actor: str
    key_id: str
    status: str
    latency_ms: int
    timestamp: str
    error_summary: str


class ListAuditEventsOutput(TypedDict):
    tenant_id: str
    events: list[AuditEventOut]
    count: int
