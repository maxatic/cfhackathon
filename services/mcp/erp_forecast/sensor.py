"""Session-scoped sensor personalization for Swiftron predictions."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from time import time

from .real_model import get_default_model


@dataclass(frozen=True)
class _SensorSession:
    """Cached personalization context."""

    client_id: str
    additional_tokens: list[str]
    created_at: float


_SESSIONS: dict[str, _SensorSession] = {}


def apply_sensor(
    client_id: str,
    additional_tokens: list[str],
) -> str:
    """Create a sensor session and return its opaque id.

    Example:
        `apply_sensor("nexus_lab_solutions", ["token_a", "token_b"])` returns `"session_..."`.
    """
    if not additional_tokens:
        raise ValueError("additional_tokens must include at least one token.")

    model = get_default_model()
    if client_id not in model.list_clients():
        raise ValueError(f"Unknown client_id={client_id}.")

    normalized_tokens = [str(token).strip() for token in additional_tokens if str(token).strip()]
    if not normalized_tokens:
        raise ValueError("additional_tokens must include at least one non-empty token.")

    digest = sha256(f"{client_id}:{','.join(normalized_tokens)}:{time()}".encode("utf-8")).hexdigest()[:16]
    session_id = f"session_{digest}"
    _SESSIONS[session_id] = _SensorSession(
        client_id=client_id,
        additional_tokens=normalized_tokens,
        created_at=time(),
    )
    return session_id


def predict_with_session(
    session_id: str,
    start_sequence: list[str] | None,
    max_generate: int = 32,
    top_k: int = 5,
    temperature: float = 1.0,
    seed: int | None = None,
) -> dict[str, object]:
    """Predict with the sensor profile tied to `session_id`.

    Example:
        `predict_with_session("session_abc", [], max_generate=2)` returns the same shape as
        `predict_basket`, with a `sensor_profile` decoder strategy.
    """
    session = _SESSIONS.get(session_id)
    if session is None:
        raise ValueError(f"Unknown session_id={session_id}.")
    return get_default_model().predict_basket(
        client_id=session.client_id,
        start_sequence=start_sequence,
        max_generate=max_generate,
        top_k=top_k,
        temperature=temperature,
        seed=seed,
        sensor_tokens=session.additional_tokens,
    )
