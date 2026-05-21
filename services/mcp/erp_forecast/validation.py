"""Input validation helpers for Lane A tool wrappers.

Every tool runs untrusted input from one of two surfaces: an MCP `tools/call`
payload (where FastMCP runs Pydantic schema validation before the function
body) and a Starlette REST handler (where the body is a free-form dict and
no schema runs). Validators in this module are called from inside the tool
body so they execute on both paths. Failures raise `ValueError` so the
active `_AuditContext` records them.

Bounds are documented per validator. Bound choices reflect what the
Swiftron ONNX wrapper accepts (see `real_model.py`) plus DoS-shaped
ceilings for free-form list parameters.
"""

from __future__ import annotations

from typing import Any


MAX_START_SEQUENCE_TOKENS = 256
MAX_ADDITIONAL_TOKENS = 64
MAX_RAW_ROWS = 2000
MAX_CLIENT_ID_LEN = 128
MAX_OBJECTIVE_TEXT_LEN = 1024


def coerce_int(
    value: Any,
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Coerce `value` to an int in `[minimum, maximum]`. None falls back to `default`.

    Raises `ValueError` with a clear, agent-recoverable message on bad type or
    out-of-range numbers.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, got boolean.")
    if isinstance(value, int):
        candidate = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{name} must be a whole number, got {value!r}.")
        candidate = int(value)
    elif isinstance(value, str):
        try:
            candidate = int(value)
        except ValueError:
            raise ValueError(
                f"{name} must be an integer, got the string {value!r}."
            ) from None
    else:
        raise ValueError(
            f"{name} must be an integer, got {type(value).__name__}."
        )
    if candidate < minimum or candidate > maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}, got {candidate}."
        )
    return candidate


def coerce_optional_int(
    value: Any,
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    """Coerce to an int or None. Bounds applied only when value is provided."""
    if value is None:
        return None
    coerced = coerce_int(
        value,
        name,
        default=0,
        minimum=minimum if minimum is not None else -(2**31),
        maximum=maximum if maximum is not None else (2**31 - 1),
    )
    return coerced


def coerce_float(
    value: Any,
    name: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    """Coerce `value` to a float in `[minimum, maximum]`. None falls back to `default`."""
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, got boolean.")
    if isinstance(value, (int, float)):
        candidate = float(value)
    elif isinstance(value, str):
        try:
            candidate = float(value)
        except ValueError:
            raise ValueError(
                f"{name} must be a number, got the string {value!r}."
            ) from None
    else:
        raise ValueError(f"{name} must be a number, got {type(value).__name__}.")
    if candidate < minimum or candidate > maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}, got {candidate}."
        )
    return candidate


def coerce_str(value: Any, name: str, *, default: str = "", max_len: int) -> str:
    """Coerce optional string with a length cap. None falls back to `default`."""
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}.")
    if len(value) > max_len:
        raise ValueError(
            f"{name} is too long ({len(value)} chars). Maximum is {max_len}."
        )
    return value


def coerce_client_id(value: Any) -> str:
    """Coerce `client_id` to a non-empty string within length limits."""
    if value is None:
        raise ValueError("client_id is required.")
    if not isinstance(value, str):
        raise ValueError(
            f"client_id must be a string, got {type(value).__name__}."
        )
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("client_id must be a non-empty string.")
    if len(cleaned) > MAX_CLIENT_ID_LEN:
        raise ValueError(
            f"client_id is too long ({len(cleaned)} chars). Maximum is "
            f"{MAX_CLIENT_ID_LEN}."
        )
    return cleaned


def coerce_token_list(
    value: Any,
    name: str,
    *,
    allow_none: bool,
    allow_empty: bool,
    max_len: int,
) -> list[str] | None:
    """Coerce a list-of-strings parameter.

    Catches the common bug where a caller passes a single string and Python
    silently iterates its characters: we require a JSON array.
    """
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{name} is required.")
    if isinstance(value, str):
        raise ValueError(
            f"{name} must be a JSON array of strings, got a single string. "
            f"Wrap individual tokens in a list, for example [\"{value}\"]."
        )
    if not isinstance(value, list):
        raise ValueError(
            f"{name} must be a JSON array of strings, got {type(value).__name__}."
        )
    if not allow_empty and len(value) == 0:
        raise ValueError(f"{name} must include at least one token.")
    if len(value) > max_len:
        raise ValueError(
            f"{name} contains {len(value)} tokens. Maximum is {max_len}."
        )
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(
                f"{name}[{index}] must be a string, got "
                f"{type(item).__name__}."
            )
    return list(value)


def coerce_raw_rows(value: Any) -> list[dict[str, Any]]:
    """Coerce `raw_rows` for `anonymize_and_tokenize_orders`.

    Each row must be a JSON object. Catches the common error of passing a
    flat list of scalars and surfacing a raw Python `'int' object is not
    iterable` to the caller.
    """
    if value is None:
        raise ValueError("raw_rows is required.")
    if not isinstance(value, list):
        raise ValueError(
            f"raw_rows must be a JSON array of objects, got "
            f"{type(value).__name__}."
        )
    if len(value) == 0:
        raise ValueError("raw_rows must include at least one order row.")
    if len(value) > MAX_RAW_ROWS:
        raise ValueError(
            f"raw_rows contains {len(value)} rows. Maximum is {MAX_RAW_ROWS}."
        )
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise ValueError(
                f"raw_rows[{index}] must be a JSON object, got "
                f"{type(row).__name__}."
            )
    return list(value)


_CLIENT_LIST_PATTERN = "Available clients:"


def shorten_client_list_error(message: str, *, max_ids: int = 12) -> str:
    """Trim long 'Unknown client_id ... Available clients: a, b, c, ...' messages.

    Lane C's wrapper currently dumps all 169 known client ids when the model
    fails to find one. That makes the error long, distracts an agent reading
    it, and leaks every id over the wire. We keep the unknown-id prefix
    intact and point the agent to `list_clients` instead.
    """
    if _CLIENT_LIST_PATTERN not in message:
        return message
    prefix, _, tail = message.partition(_CLIENT_LIST_PATTERN)
    ids_part = tail.strip().rstrip(".")
    if not ids_part:
        return message
    ids = [item.strip() for item in ids_part.split(",") if item.strip()]
    if len(ids) <= max_ids:
        return message
    head = ", ".join(ids[:max_ids])
    return (
        f"{prefix.rstrip()} Call list_clients to see all available client ids. "
        f"First {max_ids} known ids: {head}, ..."
    )
