from __future__ import annotations

import re
from hashlib import sha256
from typing import Any, Iterable, Mapping

from .data import OrderRecord


SENSITIVE_FIELD_HINTS = {
    "customer_id",
    "customer_name",
    "name",
    "email",
    "phone",
    "address",
    "ship_to_address",
    "billing_address",
    "po_number",
    "contact",
}
HASH_FIELD_HINTS = {"customer_id", "customer_name", "name", "email", "phone", "contact"}
SCRUB_FIELD_HINTS = {"address", "ship_to_address", "billing_address", "po_number"}
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?:\+?\d[\d .()/-]{7,}\d)")
ADDRESS_PATTERN = re.compile(r"\b\d{1,6}\s+[A-Za-z0-9 .'-]+\s+(?:st|street|ave|avenue|rd|road|blvd|drive|dr)\b", re.IGNORECASE)
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _hash_value(value: str, salt: str) -> str:
    digest = sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()
    return digest[:12]


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_").replace(" ", "_")


def _field_matches(key: str, hints: set[str]) -> bool:
    normalized = _normalize_key(key)
    return any(hint in normalized for hint in hints)


def _row_to_mapping(row: OrderRecord | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(row, OrderRecord):
        return row.to_dict()
    return dict(row)


def _detect_sensitive_fields(rows: list[dict[str, Any]]) -> list[str]:
    detected: set[str] = set()
    for row in rows:
        for key, value in row.items():
            text = "" if value is None else str(value)
            if (
                _field_matches(key, SENSITIVE_FIELD_HINTS)
                or EMAIL_PATTERN.search(text)
                or _looks_like_phone(text)
                or ADDRESS_PATTERN.search(text)
            ):
                detected.add(key)
    return sorted(detected)


def _looks_like_phone(value: str) -> bool:
    stripped = value.strip()
    if DATE_PATTERN.match(stripped):
        return False
    if not PHONE_PATTERN.search(stripped):
        return False
    digits = [character for character in stripped if character.isdigit()]
    return len(digits) >= 10


def _customer_source(row: Mapping[str, Any]) -> str:
    for key in ("customer_id", "customer_name", "email", "contact_email", "account_id", "account_name"):
        if key in row and row[key] not in (None, ""):
            return str(row[key])
    return "|".join(str(row.get(key, "")) for key in sorted(row))


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def anonymize_orders(
    orders: Iterable[OrderRecord | Mapping[str, Any]],
    salt: str = "swiftforecast-demo",
    sample_size: int = 50,
) -> dict[str, object]:
    """Return anonymized ERP rows plus a deterministic privacy audit report."""
    rows = [_row_to_mapping(order) for order in orders]
    if sample_size < 1 or sample_size > 500:
        raise ValueError("sample_size must be between 1 and 500.")

    detected_sensitive_fields = _detect_sensitive_fields(rows)
    fields_hashed = sorted(
        {
            field
            for row in rows
            for field in row
            if _field_matches(field, HASH_FIELD_HINTS) or field in detected_sensitive_fields
        }
        - {
            field
            for row in rows
            for field in row
            if _field_matches(field, SCRUB_FIELD_HINTS)
        }
    )
    fields_scrubbed = sorted(
        {
            field
            for row in rows
            for field in row
            if _field_matches(field, SCRUB_FIELD_HINTS)
        }
    )

    anonymized = []
    for row in rows[:sample_size]:
        customer_ref = f"cust_{_hash_value(_customer_source(row), salt)}"
        unit_price = _coerce_float(row.get("unit_price", row.get("price", 0)))
        anonymized.append(
            {
                "tenant_id": row.get("tenant_id", "raw_upload"),
                "customer_ref": customer_ref,
                "customer_segment": row.get("customer_segment", row.get("segment", "unknown")),
                "region": row.get("region", "unknown"),
                "sku": row.get("sku", row.get("product_sku", "unknown")),
                "order_date": row.get("order_date", row.get("order_week", "unknown")),
                "quantity": _coerce_int(row.get("quantity", row.get("qty", 0))),
                "unit_price_bucket": _price_bucket(unit_price),
                "promotion": _coerce_bool(row.get("promotion", row.get("promotion_flag", False))),
                "stockout": _coerce_bool(row.get("stockout", row.get("stockout_flag", False))),
                "lead_time_days": _coerce_int(row.get("lead_time_days", 0)),
            }
        )

    return {
        "row_count": len(rows),
        "source_rows": len(rows),
        "sample_size": len(anonymized),
        "fields_scrubbed": fields_scrubbed,
        "fields_hashed": fields_hashed,
        "detected_sensitive_fields": detected_sensitive_fields,
        "removed_fields": fields_scrubbed,
        "transformed_fields": sorted({"customer_ref", "unit_price_bucket", *fields_hashed}),
        "k_anonymity_proxy": _k_anonymity_proxy(anonymized),
        "privacy_notes": [
            "Direct customer identifiers are replaced with deterministic salted hashes.",
            "Detected address and purchase-order fields are scrubbed from output rows.",
            "Prices are bucketed before rows are exposed to agents.",
        ],
        "k_anonymity_note": "Rows preserve segment, region, week, and demand signal while removing direct customer identifiers.",
        "sample": anonymized,
    }


def _k_anonymity_proxy(rows: list[dict[str, Any]]) -> int:
    buckets: dict[tuple[Any, Any], int] = {}
    for row in rows:
        key = (row.get("customer_segment"), row.get("region"))
        buckets[key] = buckets.get(key, 0) + 1
    return min(buckets.values()) if buckets else 0


def _price_bucket(price: float) -> str:
    if price < 50:
        return "0-50"
    if price < 150:
        return "50-150"
    if price < 300:
        return "150-300"
    return "300+"
