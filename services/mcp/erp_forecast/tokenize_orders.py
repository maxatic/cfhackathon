"""PII scrub and Swiftron vocabulary mapping for uploaded order rows."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .privacy import anonymize_orders
from .real_model import get_default_model


def anonymize_and_tokenize(
    raw_rows: list[dict[str, Any]],
    client_id: str,
) -> dict[str, object]:
    """Scrub raw rows, then map product fields to the mounted client's vocabulary.

    Example:
        `anonymize_and_tokenize([{"product_sku": "SKU-1", "order_date": "2026-05-01"}],
        "nexus_lab_solutions")` returns token arrays plus an audit report.
    """
    if not raw_rows:
        raise ValueError("raw_rows must include at least one order row.")

    model = get_default_model()
    vocab = model.vocab_for_client(client_id)
    audit = anonymize_orders(raw_rows, sample_size=min(max(len(raw_rows), 1), 500))
    sorted_rows = sorted(enumerate(raw_rows), key=lambda item: _row_date(item[1]) or date.min)

    tokenized: list[str] = []
    time_deltas: list[int] = []
    rows: list[dict[str, object]] = []
    previous_date: date | None = None

    for position, (source_index, row) in enumerate(sorted_rows, start=1):
        token = _map_row_to_vocab(row, vocab)
        current_date = _row_date(row)
        delta = _date_delta(previous_date, current_date)
        if current_date is not None:
            previous_date = current_date
        tokenized.append(token)
        time_deltas.append(delta)
        rows.append(
            {
                "row_id": str(row.get("row_id", f"row_{position:03d}")),
                "source_label": _source_label(row, source_index),
                "token": token,
                "time_delta": delta,
            }
        )

    return {
        "client_id": client_id,
        "tokenized": tokenized,
        "time_deltas": time_deltas,
        "audit_report": {
            "row_count": int(audit["row_count"]),
            "fields_hashed": list(audit["fields_hashed"]),
            "fields_scrubbed": list(audit["fields_scrubbed"]),
            "detected_sensitive_fields": list(audit["detected_sensitive_fields"]),
            "k_anonymity_proxy": int(audit["k_anonymity_proxy"]),
            "privacy_notes": list(audit["privacy_notes"]),
        },
        "rows": rows,
    }


def _map_row_to_vocab(row: dict[str, Any], vocab: list[str]) -> str:
    """Return the best vocabulary token for one row."""
    normalized_vocab = {_normalize_token(token): token for token in vocab}
    for candidate in _candidate_terms(row):
        if candidate in vocab:
            return candidate
        normalized = _normalize_token(candidate)
        if normalized in normalized_vocab:
            return normalized_vocab[normalized]
        for vocab_key, vocab_token in normalized_vocab.items():
            if normalized and (normalized in vocab_key or vocab_key in normalized):
                return vocab_token
    if "<unk>" in vocab:
        return "<unk>"
    for token in vocab:
        if not str(token).startswith("<dt_"):
            return str(token)
    raise ValueError("Client vocabulary is empty.")


def _candidate_terms(row: dict[str, Any]) -> list[str]:
    """Extract possible product identifiers from a raw order row."""
    fields = (
        "token",
        "product_token",
        "sku",
        "product_sku",
        "product_id",
        "product_name",
        "item_name",
        "source_label",
    )
    return [str(row[field]).strip() for field in fields if row.get(field) not in (None, "")]


def _normalize_token(value: str) -> str:
    """Normalize user product text and model tokens for matching."""
    return re.sub(r"[^a-z0-9]+", "", value.lower().strip("<>"))


def _row_date(row: dict[str, Any]) -> date | None:
    """Parse the order date from common ERP field names."""
    value = row.get("order_date", row.get("order_week", row.get("date")))
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _date_delta(previous: date | None, current: date | None) -> int:
    """Return days since the previous dated row."""
    if current is None or previous is None:
        return 0
    return max(0, (current - previous).days)


def _source_label(row: dict[str, Any], source_index: int) -> str:
    """Return a non-sensitive row label for dashboard display."""
    for field in ("source_label", "product_name", "item_name", "sku", "product_sku"):
        if row.get(field):
            return str(row[field])
    return f"Order row {source_index + 1}"
