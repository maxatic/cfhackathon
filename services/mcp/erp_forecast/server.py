"""SwiftForecast MCP server: dual FastMCP + Starlette REST surface.

Tools, resources, and prompts described in AGENTS.md are registered onto the
`mcp` instance below. Each tool wraps a Lane C implementation
(real_model, sensor, tokenize_orders) inside an `_AuditContext` so latency and
identity land in the audit log.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from importlib import import_module
from os import getenv
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from .audit import _AuditContext
from .auth import AuthorizationError, validate_bearer_token
from .store import STORE
from .tool_schemas import DEMO_TENANT_ID, SCOPE_FOR_TOOL


mcp = FastMCP("SwiftForecast ERP", stateless_http=True, json_response=True)


def _load_real_model() -> Any:
    """Lazy-import Lane C's real_model so server boots without it."""
    return import_module("erp_forecast.real_model")


def _load_sensor() -> Any:
    """Lazy-import Lane C's sensor module."""
    return import_module("erp_forecast.sensor")


def _load_tokenize_orders() -> Any:
    """Lazy-import Lane C's tokenize_orders module."""
    return import_module("erp_forecast.tokenize_orders")


def _model_version() -> str:
    """Pull MODEL_VERSION constant from real_model, or fall back to default."""
    try:
        return str(_load_real_model().MODEL_VERSION)
    except Exception:
        return "swiftron-onnx-v1"


async def healthz(_request: Request) -> JSONResponse:
    """Plain liveness probe for Docker and Vercel."""
    return JSONResponse({"ok": True, "service": "swiftforecast-erp-mcp"})


def _err(exc: Exception, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=status)


async def _read_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object.")
    return body


class BearerAuthMiddleware:
    """Reject /mcp requests that fail bearer-token validation."""

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
            Mount("/", app=mcp.streamable_http_app()),
        ],
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
