from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class Identity:
    subject: str
    tenant_id: str
    scopes: frozenset[str]
    plan_active: bool = True
    key_id: str = "transport"


API_KEYS: dict[str, Identity] = {
    "sk_nexus_lab_forecast_full": Identity(
        subject="agent-nexus-lab-demand-planner",
        tenant_id="nexus_lab_solutions",
        scopes=frozenset({"forecast", "anonymize", "models", "audit"}),
        key_id="key_nexus_lab_full",
    ),
}

DEMO_TOKEN_ALIASES = {
    "demo_nexus_lab_full": "sk_nexus_lab_forecast_full",
}


class AuthorizationError(ValueError):
    pass


def validate_bearer_token(token: str | None) -> Identity:
    configured = getenv("MCP_DEMO_TOKEN")
    if configured and token == configured:
        return API_KEYS["sk_nexus_lab_forecast_full"]
    normalized = DEMO_TOKEN_ALIASES.get(token or "", token)
    if normalized in API_KEYS:
        return API_KEYS[normalized]
    raise AuthorizationError(
        "Invalid API key. Use the demo key sk_nexus_lab_forecast_full or configure MCP_DEMO_TOKEN."
    )


def authorize_tool(
    tenant_id: str,
    required_scope: str,
    api_token: str | None = None,
) -> Identity:
    """Authorize tool calls while supporting both HTTP bearer auth and local demo calls."""
    if api_token:
        identity = validate_bearer_token(api_token)
        if identity.tenant_id != tenant_id:
            raise AuthorizationError("Token tenant does not match requested tenant_id.")
        if required_scope not in identity.scopes:
            raise AuthorizationError(f"Token is missing required scope: {required_scope}.")
        if not identity.plan_active:
            raise AuthorizationError("Tenant billing plan is inactive.")
        return identity

    if getenv("MCP_TRUST_TRANSPORT_AUTH", "true").lower() == "true":
        return Identity(
            subject="transport-authenticated-agent",
            tenant_id=tenant_id,
            scopes=frozenset({"forecast", "anonymize", "models", "audit"}),
            key_id="transport-trusted",
        )

    raise AuthorizationError("api_token is required when MCP_TRUST_TRANSPORT_AUTH is false.")
