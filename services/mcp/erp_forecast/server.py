from __future__ import annotations

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
from .real_model import RealSequenceModel


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
    return JSONResponse({"ok": True, "service": "swiftforecast-erp-mcp"})


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
                response = Response("Unauthorized", status_code=401)
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
            Route("/api/real-sequence", rest_real_sequence, methods=["POST"]),
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
