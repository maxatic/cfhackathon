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


@mcp.tool()
def predict_next_basket(
    client_id: str = DEMO_TENANT_ID,
    start_sequence: list[str] | None = None,
    max_generate: int = 32,
    top_k: int = 5,
    temperature: float = 1.0,
    seed: int | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Top-k autoregressive prediction. Returns ordered tokens with time deltas."""
    with _AuditContext(
        STORE,
        "predict_next_basket",
        DEMO_TENANT_ID,
        SCOPE_FOR_TOOL["predict_next_basket"],
        api_token,
    ):
        try:
            real_model = _load_real_model()
            result = real_model.get_default_model().predict_basket(
                client_id=client_id,
                start_sequence=start_sequence,
                max_generate=max_generate,
                top_k=top_k,
                temperature=temperature,
                seed=seed,
            )
        except Exception as exc:
            raise ValueError(f"predict_next_basket failed: {exc}") from exc
        STORE.record_latest_prediction("predict_next_basket", result)
        return result


@mcp.tool()
def predict_scenarios(
    client_id: str = DEMO_TENANT_ID,
    start_sequence: list[str] | None = None,
    beam_width: int = 4,
    horizon: int = 16,
    temperature: float = 1.0,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Beam search over the decoder. Returns ranked trajectories with joint log-prob."""
    with _AuditContext(
        STORE,
        "predict_scenarios",
        DEMO_TENANT_ID,
        SCOPE_FOR_TOOL["predict_scenarios"],
        api_token,
    ):
        try:
            real_model = _load_real_model()
            scenarios = real_model.get_default_model().run_beam(
                client_id=client_id,
                start_sequence=start_sequence,
                beam_width=beam_width,
                horizon=horizon,
                temperature=temperature,
            )
        except Exception as exc:
            raise ValueError(f"predict_scenarios failed: {exc}") from exc
        payload = {
            "client_id": client_id,
            "scenarios": scenarios,
            "model_version": _model_version(),
            "decoder_config": {
                "strategy": "beam_search",
                "beam_width": beam_width,
                "horizon": horizon,
                "temperature": temperature,
            },
        }
        STORE.record_latest_prediction("predict_scenarios", payload)
        return payload


_BEAM_KEYWORDS = (
    "scenario",
    "scenarios",
    "alternative",
    "alternatives",
    "compare",
    "comparison",
    "best case",
    "worst case",
    "what if",
    "options",
    "trajector",
    "ranked",
)


def _pick_forecast_strategy(objective_text: str) -> tuple[str, str]:
    """Pick decoder strategy from the agent's objective text.

    Returns (strategy, rationale).
    """
    lowered = (objective_text or "").lower()
    if any(keyword in lowered for keyword in _BEAM_KEYWORDS):
        return "beam_search", (
            "Objective mentions scenario comparison or ranked alternatives, so "
            "the server ran beam search to expose joint log-probabilities."
        )
    return "top_k", (
        "Objective reads as a single most-likely next basket, so the server "
        "ran top-k autoregressive decoding."
    )


@mcp.tool()
def forecast_plan(
    client_id: str = DEMO_TENANT_ID,
    objective_text: str = "",
    horizon_hint: int | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Adaptive planner. Picks greedy or beam from `objective_text`, then calls it."""
    with _AuditContext(
        STORE,
        "forecast_plan",
        DEMO_TENANT_ID,
        SCOPE_FOR_TOOL["forecast_plan"],
        api_token,
    ):
        strategy, rationale = _pick_forecast_strategy(objective_text)
        try:
            real_model = _load_real_model()
            model = real_model.get_default_model()
            if strategy == "beam_search":
                horizon = max(4, min(int(horizon_hint or 12), 32))
                inner: dict[str, Any] = {
                    "client_id": client_id,
                    "scenarios": model.run_beam(
                        client_id=client_id,
                        start_sequence=None,
                        beam_width=4,
                        horizon=horizon,
                        temperature=1.0,
                    ),
                    "decoder_config": {
                        "strategy": "beam_search",
                        "beam_width": 4,
                        "horizon": horizon,
                        "temperature": 1.0,
                    },
                }
            else:
                max_generate = max(4, min(int(horizon_hint or 16), 48))
                inner = model.predict_basket(
                    client_id=client_id,
                    start_sequence=None,
                    max_generate=max_generate,
                    top_k=5,
                    temperature=1.0,
                    seed=None,
                )
        except Exception as exc:
            raise ValueError(f"forecast_plan failed: {exc}") from exc

        payload = {
            "client_id": client_id,
            "chosen_strategy": strategy,
            "rationale": rationale,
            "payload": inner,
            "model_version": _model_version(),
        }
        STORE.record_latest_prediction("forecast_plan", payload)
        return payload


@mcp.tool()
def personalize_client(
    client_id: str = DEMO_TENANT_ID,
    additional_tokens: list[str] | None = None,
    start_sequence: list[str] | None = None,
    max_generate: int = 32,
    top_k: int = 5,
    temperature: float = 1.0,
    seed: int | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Build a sensor session from `additional_tokens`, then predict with it."""
    with _AuditContext(
        STORE,
        "personalize_client",
        DEMO_TENANT_ID,
        SCOPE_FOR_TOOL["personalize_client"],
        api_token,
    ):
        if not additional_tokens:
            raise ValueError("additional_tokens must include at least one token.")
        try:
            sensor = _load_sensor()
            session_id = sensor.apply_sensor(client_id, list(additional_tokens))
            prediction = sensor.predict_with_session(
                session_id=session_id,
                start_sequence=start_sequence,
                max_generate=max_generate,
                top_k=top_k,
                temperature=temperature,
                seed=seed,
            )
        except Exception as exc:
            raise ValueError(f"personalize_client failed: {exc}") from exc
        payload = {
            "session_id": session_id,
            "client_id": client_id,
            "additional_tokens": list(additional_tokens),
            "prediction": prediction,
        }
        STORE.record_latest_prediction("personalize_client", payload)
        return payload


@mcp.tool()
def anonymize_and_tokenize_orders(
    raw_rows: list[dict[str, Any]],
    client_id: str = DEMO_TENANT_ID,
    api_token: str | None = None,
) -> dict[str, Any]:
    """PII scrub raw ERP rows, then map them to the client's Swiftron vocabulary."""
    with _AuditContext(
        STORE,
        "anonymize_and_tokenize_orders",
        DEMO_TENANT_ID,
        SCOPE_FOR_TOOL["anonymize_and_tokenize_orders"],
        api_token,
    ):
        try:
            tokenize_orders = _load_tokenize_orders()
            result = tokenize_orders.anonymize_and_tokenize(
                raw_rows=raw_rows,
                client_id=client_id,
            )
        except Exception as exc:
            raise ValueError(f"anonymize_and_tokenize_orders failed: {exc}") from exc
        return result


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


async def rest_predict(request: Request) -> JSONResponse:
    try:
        body = await _read_body(request)
        return JSONResponse(
            predict_next_basket(
                client_id=body.get("client_id", DEMO_TENANT_ID),
                start_sequence=body.get("start_sequence"),
                max_generate=int(body.get("max_generate", 32)),
                top_k=int(body.get("top_k", 5)),
                temperature=float(body.get("temperature", 1.0)),
                seed=body.get("seed"),
                api_token=body.get("api_token"),
            )
        )
    except (ValueError, AuthorizationError, ImportError, RuntimeError) as exc:
        return _err(exc)


async def rest_scenarios(request: Request) -> JSONResponse:
    try:
        body = await _read_body(request)
        return JSONResponse(
            predict_scenarios(
                client_id=body.get("client_id", DEMO_TENANT_ID),
                start_sequence=body.get("start_sequence"),
                beam_width=int(body.get("beam_width", 4)),
                horizon=int(body.get("horizon", 16)),
                temperature=float(body.get("temperature", 1.0)),
                api_token=body.get("api_token"),
            )
        )
    except (ValueError, AuthorizationError, ImportError, RuntimeError) as exc:
        return _err(exc)


async def rest_forecast_plan(request: Request) -> JSONResponse:
    try:
        body = await _read_body(request)
        return JSONResponse(
            forecast_plan(
                client_id=body.get("client_id", DEMO_TENANT_ID),
                objective_text=str(body.get("objective_text", "")),
                horizon_hint=body.get("horizon_hint"),
                api_token=body.get("api_token"),
            )
        )
    except (ValueError, AuthorizationError, ImportError, RuntimeError) as exc:
        return _err(exc)


async def rest_personalize(request: Request) -> JSONResponse:
    try:
        body = await _read_body(request)
        return JSONResponse(
            personalize_client(
                client_id=body.get("client_id", DEMO_TENANT_ID),
                additional_tokens=body.get("additional_tokens"),
                start_sequence=body.get("start_sequence"),
                max_generate=int(body.get("max_generate", 32)),
                top_k=int(body.get("top_k", 5)),
                temperature=float(body.get("temperature", 1.0)),
                seed=body.get("seed"),
                api_token=body.get("api_token"),
            )
        )
    except (ValueError, AuthorizationError, ImportError, RuntimeError) as exc:
        return _err(exc)


async def rest_anonymize(request: Request) -> JSONResponse:
    try:
        body = await _read_body(request)
        raw_rows = body.get("raw_rows")
        if not isinstance(raw_rows, list):
            raise ValueError("raw_rows must be a JSON array of objects.")
        return JSONResponse(
            anonymize_and_tokenize_orders(
                raw_rows=raw_rows,
                client_id=body.get("client_id", DEMO_TENANT_ID),
                api_token=body.get("api_token"),
            )
        )
    except (ValueError, AuthorizationError, ImportError, RuntimeError) as exc:
        return _err(exc)


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
            Route("/api/predict", rest_predict, methods=["POST"]),
            Route("/api/scenarios", rest_scenarios, methods=["POST"]),
            Route("/api/forecast-plan", rest_forecast_plan, methods=["POST"]),
            Route("/api/personalize", rest_personalize, methods=["POST"]),
            Route("/api/anonymize", rest_anonymize, methods=["POST"]),
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
