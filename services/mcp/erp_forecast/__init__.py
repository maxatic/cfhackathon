"""Synthetic ERP order forecasting core for the SwiftForecast MCP demo."""

from .data import OrderRecord, generate_synthetic_erp_dataset
from .jobs import get_store
from .model import MiniTransformerForecaster

__all__ = [
    "MiniTransformerForecaster",
    "OrderRecord",
    "generate_synthetic_erp_dataset",
    "get_store",
]
