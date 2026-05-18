from __future__ import annotations

import json
from contextlib import asynccontextmanager
from os import getenv
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from .auth import AuthorizationError, validate_bearer_token
from .jobs import get_store
from .real_model import RealSequenceModel


MCP_ENDPOINT = getenv("MCP_ENDPOINT", "http://localhost:8000/mcp")
AUTH_SERVER = getenv("SUPABASE_AUTH_SERVER", "https://example.supabase.co/auth/v1")
RESOURCE_METADATA_URL = getenv(
    "MCP_RESOURCE_METADATA_URL",
    "http://localhost:8000/.well-known/oauth-protected-resource",
)

mcp = FastMCP("SwiftForecast ERP", stateless_http=True, json_response=True)
_REAL_MODEL: RealSequenceModel | None = None


def get_real_model() -> RealSequenceModel:
    global _REAL_MODEL
    artifact_dir = getenv("REAL_MODEL_ARTIFACT_DIR")
    if not artifact_dir:
        raise ValueError(
            "REAL_MODEL_ARTIFACT_DIR is not set. Mount the NDA bundle containing "
            "landing_page_model.onnx, multi_client_dataset.joblib, alit_backend.py, "
            "and pyarmor_runtime_000000."
        )
    if _REAL_MODEL is None:
        _REAL_MODEL = RealSequenceModel(artifact_dir)
    return _REAL_MODEL


@mcp.tool()
def erp_forecast_orders(
    tenant_id: str,
    sku: str,
    customer_segment: str = "all",
    horizon_weeks: int = 12,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Forecast future ERP order quantities for one tenant, SKU, and customer segment.

    Use this when an agent needs a concise, structured demand forecast. The
    optional api_token can be one of the demo tokens such as demo_northstar_full
    for local or STDIO testing. HTTP deployments should send a bearer token too.
    """
    return get_store().forecast_orders(tenant_id, sku, customer_segment, horizon_weeks, api_token)


@mcp.tool()
def erp_beam_search_forecast(
    tenant_id: str,
    sku: str,
    customer_segment: str = "all",
    horizon_weeks: int = 12,
    beam_width: int = 4,
    temperature: float = 1.0,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Generate ranked autoregressive forecast scenarios using beam search.

    Use this after erp_forecast_orders when the agent needs alternative demand
    paths, such as promotion lift, supply delay, or stockout drag scenarios.
    Increase temperature to explore lower-probability alternatives; lower it for
    conservative planning.
    """
    return get_store().beam_search_forecast(
        tenant_id, sku, customer_segment, horizon_weeks, beam_width, temperature, api_token
    )


@mcp.tool()
def erp_adaptive_forecast_plan(
    tenant_id: str,
    sku: str,
    objective: str,
    customer_segment: str = "all",
    horizon_weeks: int | None = None,
    strategy: str = "auto",
    beam_width: int | None = None,
    temperature: float | None = None,
    recommendation_count: int = 3,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Let an agent choose the forecast workflow and decoding parameters.

    Use this as the main CTO-challenge tool when the user describes a business
    goal instead of a fixed API call, for example: "what should I prepare for a
    customer visit next week?", "forecast inventory for the next 50 orders", or
    "explore substitutes with more creative beam search." The tool selects
    greedy or beam search, horizon, beam width, temperature, and optional product
    recommendations while keeping the tenant/client fixed.
    """
    return get_store().adaptive_forecast_plan(
        tenant_id,
        sku,
        objective,
        customer_segment,
        horizon_weeks,
        strategy,
        beam_width,
        temperature,
        recommendation_count,
        api_token,
    )


@mcp.tool()
def erp_real_sequence_forecast(
    client_id: str = "nexus_lab_solutions",
    start_sequence: str | None = None,
    max_generate: int = 30,
    temperature: float = 1.0,
    top_k: int = 30,
    seed: int = 42,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Run the NDA-provided ONNX sequence model through its public adapter.

    This tool is available when REAL_MODEL_ARTIFACT_DIR points at the CTO bundle.
    It treats alit_backend as protected IP and only uses the public
    SimulationDataset interface shown in the notebook.
    """
    if api_token:
        validate_bearer_token(api_token)
    return get_real_model().predict(
        client_id=client_id,
        start_sequence=start_sequence,
        max_generate=max_generate,
        temperature=temperature,
        top_k=top_k,
        seed=seed,
    ).to_dict()


@mcp.tool()
def erp_rank_at_risk_customers(
    tenant_id: str,
    sku: str,
    horizon_weeks: int = 12,
    limit: int = 5,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Rank customers by downside order risk for one SKU.

    Use this for CFO or demand-planning questions like "which customers are most
    likely to reduce orders?" The tool compares each customer's recent run rate
    with the lowest plausible beam-search scenario, then returns a ranked list
    with demand exposure, revenue at risk, and recommended intervention.
    """
    return get_store().rank_at_risk_customers(tenant_id, sku, horizon_weeks, limit, api_token)


@mcp.tool()
def erp_anonymize_orders(
    tenant_id: str,
    sku: str | None = None,
    customer_segment: str = "all",
    sample_size: int = 50,
    raw_order_rows: list[dict[str, Any]] | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Create an anonymized ERP order export sample and privacy report.

    Use this before sharing seeded order history or raw uploaded ERP rows with
    an external agent or analyst. The result hashes direct customer identifiers,
    scrubs detected PII-like fields, buckets sensitive prices, and returns a
    compact audit report.
    """
    return get_store().anonymize(
        tenant_id,
        sku,
        customer_segment,
        sample_size,
        api_token,
        raw_order_rows,
    )


@mcp.tool()
def erp_trigger_retraining(
    tenant_id: str,
    reason: str = "manual demo trigger",
    api_token: str | None = None,
) -> dict[str, Any]:
    """Queue a retraining job for the tenant.

    The first response is queued, then erp_get_retraining_status advances the
    deterministic demo job through running to completed. Completion activates a
    tenant adapter model version and shifts future forecasts for the tenant.
    """
    return get_store().trigger_retraining(tenant_id, reason, api_token)


@mcp.tool()
def erp_get_retraining_status(
    tenant_id: str,
    job_id: str,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Poll retraining status, loss curve, before/after metrics, and model version."""
    return get_store().get_retraining_status(tenant_id, job_id, api_token)


@mcp.tool()
def erp_list_model_versions(
    tenant_id: str,
    api_token: str | None = None,
) -> dict[str, Any]:
    """List active and archived model versions for a tenant."""
    return get_store().list_model_versions(tenant_id, api_token)


@mcp.tool()
def erp_list_audit_events(
    tenant_id: str,
    limit: int = 20,
    api_token: str | None = None,
) -> dict[str, Any]:
    """List recent tenant-scoped MCP tool audit events."""
    return get_store().list_audit_events(tenant_id, limit, api_token)


@mcp.resource("erp://dataset-card")
def dataset_card() -> str:
    """Describe the synthetic ERP dataset available to agents."""
    return json.dumps(get_store().summary(), indent=2)


@mcp.resource("erp://model-card")
def model_card() -> str:
    """Describe the forecasting model and decoding behavior."""
    return json.dumps(
        {
            "model": "MiniTransformerForecaster",
            "version": get_store().forecaster.version,
            "architecture": "causal self-attention over weekly demand tokens with autoregressive decoding",
            "decoders": ["greedy autoregressive", "temperature-controlled beam search", "adaptive MCP forecast planner"],
            "intended_use": "B2B ERP order prediction demo for agent-compatible MCP workflows",
            "limitations": [
                "Synthetic data only",
                "Forecasts are calibrated for demo plausibility, not production procurement decisions",
                "No real customer PII should be passed to this demo service",
            ],
        },
        indent=2,
    )


@mcp.resource("erp://forecast/latest")
def latest_forecast() -> str:
    """Return the latest forecast run created during this service session."""
    return json.dumps(get_store().latest_forecast(), indent=2)


@mcp.prompt()
def demand_planning_review(tenant_id: str, sku: str, customer_segment: str = "all") -> str:
    """Guide an agent through demand planning review with forecast and scenario tools."""
    return (
        f"Review demand risk for tenant {tenant_id}, SKU {sku}, segment {customer_segment}. "
        "Start with erp_adaptive_forecast_plan and describe the business objective so "
        "the MCP server can choose greedy decoding, beam search, temperature, and horizon. "
        "If the user asks for fixed scenarios, call erp_beam_search_forecast with explicit "
        "beam_width and temperature. Compare the base path with alternatives, identify "
        "weeks with the widest uncertainty, and recommend procurement or customer-success "
        "actions. If sharing history externally, call erp_anonymize_orders before quoting "
        "row-level examples."
    )


async def healthz(_request: Request) -> JSONResponse:
    summary = get_store().summary()
    return JSONResponse(
        {
            "ok": True,
            "service": "swiftforecast-erp-mcp",
            "dataset": {
                "orders": summary["order_count"],
                "products": summary["product_count"],
                "customers": summary["customer_count"],
            },
        }
    )


async def protected_resource_metadata(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "resource": MCP_ENDPOINT,
            "authorization_servers": [AUTH_SERVER] if AUTH_SERVER != "api-key-demo" else [],
            "scopes_supported": ["forecast", "anonymize", "retrain", "models", "audit"],
            "bearer_methods_supported": ["header"],
            "api_key_supported": True,
            "api_key_header": "Authorization: Bearer <tenant-scoped-api-key>",
            "authorization_notes": (
                "This hackathon demo validates static tenant-scoped API keys. "
                "Supabase OAuth/JWKS validation is a planned production extension."
            ),
            "resource_documentation": "https://github.com/modelcontextprotocol/specification",
        }
    )


async def rest_forecast(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        result = get_store().forecast_orders(
            tenant_id=body["tenant_id"],
            sku=body["sku"],
            customer_segment=body.get("customer_segment", "all"),
            horizon_weeks=int(body.get("horizon_weeks", 12)),
            api_token=body.get("api_token"),
        )
    except (KeyError, ValueError, AuthorizationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def rest_real_sequence(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        api_token = body.get("api_token")
        if api_token:
            validate_bearer_token(api_token)
        result = get_real_model().predict(
            client_id=body.get("client_id", "nexus_lab_solutions"),
            start_sequence=body.get("start_sequence"),
            max_generate=int(body.get("max_generate", 30)),
            temperature=float(body.get("temperature", 1.0)),
            top_k=int(body.get("top_k", 30)),
            seed=int(body.get("seed", 42)),
        ).to_dict()
    except (KeyError, ValueError, ImportError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def rest_adaptive_forecast(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        result = get_store().adaptive_forecast_plan(
            tenant_id=body["tenant_id"],
            sku=body["sku"],
            objective=body["objective"],
            customer_segment=body.get("customer_segment", "all"),
            horizon_weeks=body.get("horizon_weeks"),
            strategy=body.get("strategy", "auto"),
            beam_width=body.get("beam_width"),
            temperature=body.get("temperature"),
            recommendation_count=int(body.get("recommendation_count", 3)),
            api_token=body.get("api_token"),
        )
    except (KeyError, ValueError, AuthorizationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def rest_rank_at_risk(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        result = get_store().rank_at_risk_customers(
            tenant_id=body["tenant_id"],
            sku=body["sku"],
            horizon_weeks=int(body.get("horizon_weeks", 12)),
            limit=int(body.get("limit", 5)),
            api_token=body.get("api_token"),
        )
    except (KeyError, ValueError, AuthorizationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def rest_anonymize(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        result = get_store().anonymize(
            tenant_id=body["tenant_id"],
            sku=body.get("sku"),
            customer_segment=body.get("customer_segment", "all"),
            sample_size=int(body.get("sample_size", 50)),
            api_token=body.get("api_token"),
            raw_order_rows=body.get("raw_order_rows"),
        )
    except (KeyError, ValueError, AuthorizationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def rest_trigger_retraining(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        result = get_store().trigger_retraining(
            tenant_id=body["tenant_id"],
            reason=body.get("reason", "dashboard retraining trigger"),
            api_token=body.get("api_token"),
        )
    except (KeyError, ValueError, AuthorizationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def rest_retraining_status(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        result = get_store().get_retraining_status(
            tenant_id=body["tenant_id"],
            job_id=body["job_id"],
            api_token=body.get("api_token"),
        )
    except (KeyError, ValueError, AuthorizationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def rest_model_versions(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        result = get_store().list_model_versions(
            tenant_id=body["tenant_id"],
            api_token=body.get("api_token"),
        )
    except (KeyError, ValueError, AuthorizationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def rest_audit_events(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        result = get_store().list_audit_events(
            tenant_id=body["tenant_id"],
            limit=int(body.get("limit", 20)),
            api_token=body.get("api_token"),
        )
    except (KeyError, ValueError, AuthorizationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


class BearerAuthMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and str(scope.get("path", "")).startswith("/mcp"):
            headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope["headers"]}
            auth_header = headers.get("authorization", "")
            token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None
            try:
                validate_bearer_token(token)
            except AuthorizationError:
                response = Response(
                    "Unauthorized",
                    status_code=401,
                    headers={
                        "WWW-Authenticate": (
                            f'Bearer realm="mcp", resource_metadata="{RESOURCE_METADATA_URL}", '
                            'scope="forecast anonymize retrain models audit", '
                            'error="invalid_token", error_description="Provide a tenant-scoped SwiftForecast API key."'
                        )
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app() -> Starlette:
    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/.well-known/oauth-protected-resource", protected_resource_metadata, methods=["GET"]),
            Route("/api/forecast", rest_forecast, methods=["POST"]),
            Route("/api/real-sequence", rest_real_sequence, methods=["POST"]),
            Route("/api/adaptive-forecast", rest_adaptive_forecast, methods=["POST"]),
            Route("/api/risk", rest_rank_at_risk, methods=["POST"]),
            Route("/api/anonymize", rest_anonymize, methods=["POST"]),
            Route("/api/retraining", rest_trigger_retraining, methods=["POST"]),
            Route("/api/retraining/status", rest_retraining_status, methods=["POST"]),
            Route("/api/model-versions", rest_model_versions, methods=["POST"]),
            Route("/api/audit-events", rest_audit_events, methods=["POST"]),
            Mount("/", app=mcp.streamable_http_app()),
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in getenv("CORS_ALLOW_ORIGINS", "*").split(",")],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["authorization", "content-type", "accept", "mcp-protocol-version"],
    )
    app.add_middleware(BearerAuthMiddleware)
    return app


app = create_app()
