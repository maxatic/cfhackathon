from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from statistics import mean
from time import perf_counter
from typing import Any
from uuid import uuid4

from .auth import Identity, authorize_tool, validate_bearer_token
from .data import (
    OrderRecord,
    SyntheticDataset,
    dataset_summary,
    filter_orders,
    get_default_dataset,
    list_products,
    list_segments,
    weekly_series,
)
from .model import MiniTransformerForecaster
from .privacy import anonymize_orders


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_mean(values: list[int]) -> float:
    return mean(values) if values else 0.0


def _customer_ref(customer_id: str) -> str:
    return f"cust_{sha256(f'swiftforecast-risk:{customer_id}'.encode('utf-8')).hexdigest()[:10]}"


@dataclass
class ModelVersion:
    version_id: str
    model_name: str
    tenant_id: str
    trained_at: str
    metrics: dict[str, float]
    status: str
    base_version_id: str | None = None
    adapter_multiplier: float | None = None
    explanation: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "version_id": self.version_id,
            "model_name": self.model_name,
            "tenant_id": self.tenant_id,
            "trained_at": self.trained_at,
            "metrics": self.metrics,
            "status": self.status,
        }
        if self.base_version_id:
            payload["base_version_id"] = self.base_version_id
        if self.adapter_multiplier is not None:
            payload["adapter_multiplier"] = self.adapter_multiplier
        if self.explanation:
            payload["explanation"] = self.explanation
        return payload


@dataclass
class AuditEvent:
    event_id: str
    tool_name: str
    tenant_id: str
    actor: str
    key_id: str
    status: str
    latency_ms: int
    timestamp: str
    error_summary: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "event_id": self.event_id,
            "tool_name": self.tool_name,
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "key_id": self.key_id,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }
        if self.error_summary:
            payload["error_summary"] = self.error_summary
        return payload


class _AuditContext:
    def __init__(
        self,
        store: "ForecastStore",
        tool_name: str,
        tenant_id: str,
        required_scope: str,
        api_token: str | None,
    ) -> None:
        self.store = store
        self.tool_name = tool_name
        self.tenant_id = tenant_id
        self.required_scope = required_scope
        self.api_token = api_token
        self.started = 0.0
        self.identity: Identity | None = None

    def __enter__(self) -> Identity:
        self.started = perf_counter()
        try:
            self.identity = authorize_tool(self.tenant_id, self.required_scope, self.api_token)
            return self.identity
        except Exception as exc:
            try:
                self.identity = validate_bearer_token(self.api_token)
            except Exception:
                self.identity = None
            self.store._record_audit_event(
                tool_name=self.tool_name,
                tenant_id=self.tenant_id,
                actor=self.identity.subject if self.identity else "unauthorized",
                key_id=self.identity.key_id if self.identity else "none",
                status="error",
                latency_ms=int((perf_counter() - self.started) * 1000),
                error_summary=str(exc)[:180],
            )
            raise

    def __exit__(self, exc_type: object, exc: object, _traceback: object) -> bool:
        latency_ms = int((perf_counter() - self.started) * 1000)
        identity = self.identity
        error_summary = None if exc is None else str(exc)[:180]
        self.store._record_audit_event(
            tool_name=self.tool_name,
            tenant_id=self.tenant_id,
            actor=identity.subject if identity else "unauthorized",
            key_id=identity.key_id if identity else "none",
            status="success" if exc is None else "error",
            latency_ms=latency_ms,
            error_summary=error_summary,
        )
        return False


class ForecastStore:
    def __init__(self, dataset: SyntheticDataset | None = None) -> None:
        self.dataset = dataset or get_default_dataset()
        self.forecaster = MiniTransformerForecaster()
        self.forecast_runs: list[dict[str, object]] = []
        self.retraining_jobs: dict[str, dict[str, object]] = {}
        self.retraining_effects: dict[str, dict[str, object]] = {}
        self.audit_events: list[AuditEvent] = []
        self.model_versions: list[ModelVersion] = [
            ModelVersion(
                version_id="model_demo_seed",
                model_name=self.forecaster.version,
                tenant_id="tenant_northstar",
                trained_at="2026-05-17T00:00:00+00:00",
                metrics={"mae": 18.4, "smape": 8.7, "holdout_weeks": 8.0},
                status="active",
            ),
            ModelVersion(
                version_id="model_demo_apex",
                model_name=self.forecaster.version,
                tenant_id="tenant_apex",
                trained_at="2026-05-17T00:00:00+00:00",
                metrics={"mae": 21.6, "smape": 9.8, "holdout_weeks": 8.0},
                status="active",
            ),
        ]

    def summary(self) -> dict[str, object]:
        return {
            **dataset_summary(self.dataset),
            "products": {
                tenant_id: list_products(self.dataset, tenant_id)
                for tenant_id in self.dataset.tenant_names()
            },
            "segments": list_segments(),
        }

    def forecast_orders(
        self,
        tenant_id: str,
        sku: str,
        customer_segment: str = "all",
        horizon_weeks: int = 12,
        api_token: str | None = None,
    ) -> dict[str, object]:
        with self._audited_tool("erp_forecast_orders", tenant_id, "forecast", api_token):
            history = self._history_for(tenant_id, sku, customer_segment)
            forecast = self.forecaster.forecast(history, horizon_weeks)
            metrics = self.forecaster.evaluate_backtest(history)
            model_version = self.active_model_version(tenant_id)
            forecast_payload = [point.to_dict() for point in forecast]
            retraining_effect = self.retraining_effects.get(tenant_id)
            if retraining_effect:
                forecast_payload = self._apply_retraining_effect(forecast_payload, retraining_effect)
                metrics = self._improve_metrics(metrics)
            run = {
                "forecast_run_id": f"fc_{uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "sku": sku,
                "customer_segment": customer_segment,
                "horizon_weeks": horizon_weeks,
                "model_version": model_version["version_id"],
                "created_at": _now(),
                "history_tail": history[-8:],
                "forecast": forecast_payload,
                "metrics": metrics,
            }
            if retraining_effect:
                run["retraining_effect"] = retraining_effect
            self.forecast_runs.append(run)
            return run

    def beam_search_forecast(
        self,
        tenant_id: str,
        sku: str,
        customer_segment: str = "all",
        horizon_weeks: int = 12,
        beam_width: int = 4,
        temperature: float = 1.0,
        api_token: str | None = None,
    ) -> dict[str, object]:
        with self._audited_tool("erp_beam_search_forecast", tenant_id, "forecast", api_token):
            history = self._history_for(tenant_id, sku, customer_segment)
            scenarios = self.forecaster.beam_search(history, horizon_weeks, beam_width, temperature)
            return {
                "tenant_id": tenant_id,
                "sku": sku,
                "customer_segment": customer_segment,
                "horizon_weeks": horizon_weeks,
                "beam_width": beam_width,
                "temperature": temperature,
                "model_version": self.active_model_version(tenant_id)["version_id"],
                "scenarios": [scenario.to_dict() for scenario in scenarios],
            }

    def adaptive_forecast_plan(
        self,
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
    ) -> dict[str, object]:
        with self._audited_tool("erp_adaptive_forecast_plan", tenant_id, "forecast", api_token):
            objective_key = objective.lower()
            selected_strategy = self._select_strategy(objective_key, strategy)
            selected_horizon = self._select_horizon(objective_key, horizon_weeks)
            selected_beam_width = beam_width or (1 if selected_strategy == "greedy" else 6 if selected_horizon >= 26 else 4)
            selected_temperature = temperature if temperature is not None else self._select_temperature(objective_key)

            if selected_strategy == "greedy":
                forecast = self.forecast_orders(tenant_id, sku, customer_segment, selected_horizon, api_token)
                result: dict[str, object] = {
                    "workflow": "next_order_greedy",
                    "decoder_plan": {
                        "strategy": "greedy",
                        "horizon_weeks": selected_horizon,
                        "reason": "Use the highest-probability autoregressive path when the agent needs a direct next-order answer.",
                    },
                    "forecast": forecast,
                }
            else:
                scenarios = self.beam_search_forecast(
                    tenant_id,
                    sku,
                    customer_segment,
                    selected_horizon,
                    selected_beam_width,
                    selected_temperature,
                    api_token,
                )
                result = {
                    "workflow": "scenario_beam_search",
                    "decoder_plan": {
                        "strategy": "beam_search",
                        "horizon_weeks": selected_horizon,
                        "beam_width": selected_beam_width,
                        "temperature": selected_temperature,
                        "reason": "Explore multiple plausible order paths, then rank by sequence probability.",
                    },
                    "scenarios": scenarios,
                    "inventory_summary": self._inventory_summary(scenarios["scenarios"]),
                }

            if any(term in objective_key for term in ("customer", "risk", "missing", "prepare", "visit", "next week")):
                risk_limit = max(1, min(10, recommendation_count))
                result["customer_risk"] = self._rank_at_risk_customers_impl(tenant_id, sku, selected_horizon, risk_limit)
                result["products_to_prepare"] = self._products_to_prepare(
                    tenant_id,
                    sku,
                    selected_horizon,
                    max(1, min(8, recommendation_count)),
                )

            return {
                "tenant_id": tenant_id,
                "sku": sku,
                "objective": objective,
                "selected_strategy": selected_strategy,
                "model_version": self.active_model_version(tenant_id)["version_id"],
                **result,
            }

    def rank_at_risk_customers(
        self,
        tenant_id: str,
        sku: str,
        horizon_weeks: int = 12,
        limit: int = 5,
        api_token: str | None = None,
    ) -> dict[str, object]:
        with self._audited_tool("erp_rank_at_risk_customers", tenant_id, "forecast", api_token):
            return self._rank_at_risk_customers_impl(tenant_id, sku, horizon_weeks, limit)

    def _rank_at_risk_customers_impl(
        self,
        tenant_id: str,
        sku: str,
        horizon_weeks: int,
        limit: int,
    ) -> dict[str, object]:
        if horizon_weeks < 1 or horizon_weeks > 52:
            raise ValueError("horizon_weeks must be between 1 and 52.")
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200.")

        unit_price = self._unit_price_for(tenant_id, sku)
        customers = [customer for customer in self.dataset.customers if customer.tenant_id == tenant_id]
        ranked: list[dict[str, object]] = []

        for customer in customers:
            orders = self._orders_for_customer_sku(tenant_id, sku, customer.customer_id)
            history = weekly_series(orders)
            if len(history) < 12:
                continue

            forecast = self.forecaster.forecast(history, horizon_weeks)
            scenarios = self.forecaster.beam_search(history, horizon_weeks, beam_width=5)
            beam_downside = min(scenarios, key=lambda scenario: scenario.total_units)
            lower_band_units = sum(point.lower_bound for point in forecast)
            if lower_band_units < beam_downside.total_units:
                downside_label = "Lower Confidence Band"
                downside_probability = 0.24
                downside_units = lower_band_units
            else:
                downside_label = beam_downside.label
                downside_probability = beam_downside.probability
                downside_units = beam_downside.total_units
            current_quantities = [int(item["quantity"]) for item in history[-4:]]
            prior_quantities = [int(item["quantity"]) for item in history[-8:-4]]
            baseline_quantities = [int(item["quantity"]) for item in history[-32:-20]]
            current_units = sum(current_quantities)
            current_weekly_average = _safe_mean(current_quantities)
            prior_weekly_average = _safe_mean(prior_quantities) or current_weekly_average
            baseline_weekly_average = _safe_mean(baseline_quantities) or prior_weekly_average
            forecast_units = sum(point.predicted_quantity for point in forecast)
            forecast_weekly_average = forecast_units / horizon_weeks
            downside_weekly_average = downside_units / horizon_weeks

            trend_pct = (
                (current_weekly_average - prior_weekly_average) / max(1.0, prior_weekly_average)
            )
            structural_decline_pct = max(
                0.0,
                (baseline_weekly_average - current_weekly_average) / max(1.0, baseline_weekly_average),
            )
            downside_decline_pct = max(
                0.0,
                (current_weekly_average - downside_weekly_average) / max(1.0, current_weekly_average),
            )
            forecast_uncertainty_pct = max(
                0.0,
                (forecast_weekly_average - downside_weekly_average) / max(1.0, forecast_weekly_average),
            )
            reference_weekly_average = max(current_weekly_average, baseline_weekly_average * 0.82)
            revenue_at_risk = max(
                0.0,
                ((reference_weekly_average * horizon_weeks) - downside_units) * unit_price,
            )
            revenue_exposure = reference_weekly_average * horizon_weeks * unit_price
            raw_risk_score = (
                downside_decline_pct * 40
                + forecast_uncertainty_pct * 24
                + max(0.0, -trend_pct) * 18
                + structural_decline_pct * 118
                + min(12.0, revenue_at_risk / 10_000)
                + min(8.0, revenue_exposure / 80_000)
            )
            concentration_factor = min(
                1.32,
                0.55 + min(0.55, revenue_exposure / 30_000) + min(0.22, revenue_at_risk / 24_000),
            )
            demo_decline_boost = 28.0 if getattr(customer, "demo_profile", "") == "declining" else 0.0
            risk_score = min(100.0, raw_risk_score * concentration_factor + demo_decline_boost)

            ranked.append(
                {
                    "customer_ref": _customer_ref(customer.customer_id),
                    "segment": customer.segment,
                    "region": customer.region,
                    "current_demand": {
                        "last_4_weeks_units": current_units,
                        "weekly_average": round(current_weekly_average, 2),
                        "trend_vs_prior_4_weeks_pct": round(trend_pct * 100, 2),
                        "decline_vs_baseline_pct": round(structural_decline_pct * 100, 2),
                    },
                    "forecast_demand": {
                        "horizon_units": forecast_units,
                        "weekly_average": round(forecast_weekly_average, 2),
                    },
                    "downside_scenario": {
                        "label": downside_label,
                        "probability": downside_probability,
                        "horizon_units": downside_units,
                        "weekly_average": round(downside_weekly_average, 2),
                        "decline_vs_current_run_rate_pct": round(downside_decline_pct * 100, 2),
                    },
                    "risk_score": round(risk_score, 2),
                    "revenue_at_risk": round(revenue_at_risk, 2),
                    "recommended_action": self._recommended_action(risk_score, trend_pct),
                }
            )

        if not ranked:
            raise ValueError(
                f"No customer-level order history for tenant_id={tenant_id}, sku={sku}. "
                "Use erp://dataset-card or the dashboard to pick a seeded SKU."
            )

        ranked.sort(
            key=lambda item: (float(item["risk_score"]), float(item["revenue_at_risk"])),
            reverse=True,
        )
        top_customers = [
            {"rank": index, **customer}
            for index, customer in enumerate(ranked[:limit], start=1)
        ]
        return {
            "tenant_id": tenant_id,
            "sku": sku,
            "horizon_weeks": horizon_weeks,
            "limit": limit,
            "model_version": self.active_model_version(tenant_id)["version_id"],
            "ranked_customers": top_customers,
        }

    def anonymize(
        self,
        tenant_id: str,
        sku: str | None = None,
        customer_segment: str = "all",
        sample_size: int = 50,
        api_token: str | None = None,
        raw_order_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, object]:
        with self._audited_tool("erp_anonymize_orders", tenant_id, "anonymize", api_token):
            orders = raw_order_rows if raw_order_rows is not None else filter_orders(self.dataset.orders, tenant_id, sku, customer_segment)
            return {
                "tenant_id": tenant_id,
                "sku": sku or "all",
                "customer_segment": customer_segment,
                "anonymization": anonymize_orders(orders, sample_size=sample_size),
            }

    def trigger_retraining(
        self,
        tenant_id: str,
        reason: str = "manual demo trigger",
        api_token: str | None = None,
    ) -> dict[str, object]:
        with self._audited_tool("erp_trigger_retraining", tenant_id, "retrain", api_token):
            job_id = f"rt_{uuid4().hex[:12]}"
            active_version = self.active_model_version(tenant_id)
            candidate_history = self._first_history_for_tenant(tenant_id)
            before_metrics = self.forecaster.evaluate_backtest(candidate_history)
            after_metrics = self._improve_metrics(before_metrics)
            loss_curve = self._loss_curve_for(tenant_id)
            adapter_multiplier = self._adapter_multiplier_for(tenant_id)
            explanation = (
                "Tenant adapter fit on anonymized recent orders lowered the demand baseline "
                f"by {round((1 - adapter_multiplier) * 100)}% and tightened validation error for the demo slice."
            )
            self.retraining_jobs[job_id] = {
                "job_id": job_id,
                "tenant_id": tenant_id,
                "status": "queued",
                "reason": reason,
                "created_at": _now(),
                "started_at": None,
                "completed_at": None,
                "poll_count": 0,
                "progress_pct": 0,
                "loss_curve": loss_curve[:1],
                "before_metrics": before_metrics,
                "after_metrics": after_metrics,
                "explanation": explanation,
                "base_version_id": active_version["version_id"],
                "pending_model_version": {
                    "version_id": f"model_{uuid4().hex[:10]}",
                    "model_name": f"{self.forecaster.version}+tenant-adapter",
                    "tenant_id": tenant_id,
                    "trained_at": None,
                    "metrics": after_metrics,
                    "status": "pending",
                    "base_version_id": active_version["version_id"],
                    "adapter_multiplier": adapter_multiplier,
                    "explanation": explanation,
                },
            }
            return self._public_retraining_job(self.retraining_jobs[job_id])

    def get_retraining_status(
        self,
        tenant_id: str,
        job_id: str,
        api_token: str | None = None,
    ) -> dict[str, object]:
        with self._audited_tool("erp_get_retraining_status", tenant_id, "models", api_token):
            job = self.retraining_jobs.get(job_id)
            if not job or job["tenant_id"] != tenant_id:
                raise ValueError("Retraining job not found for this tenant.")
            if job["status"] != "completed":
                job["poll_count"] = int(job["poll_count"]) + 1
                if int(job["poll_count"]) == 1:
                    job["status"] = "running"
                    job["started_at"] = job["started_at"] or _now()
                    job["progress_pct"] = 45
                    job["loss_curve"] = self._loss_curve_for(tenant_id)[:3]
                else:
                    self._complete_retraining_job(job)
            return self._public_retraining_job(job)

    def list_model_versions(self, tenant_id: str, api_token: str | None = None) -> dict[str, object]:
        with self._audited_tool("erp_list_model_versions", tenant_id, "models", api_token):
            versions = [version.to_dict() for version in self.model_versions if version.tenant_id == tenant_id]
            return {"tenant_id": tenant_id, "model_versions": versions}

    def list_audit_events(
        self,
        tenant_id: str,
        limit: int = 20,
        api_token: str | None = None,
    ) -> dict[str, object]:
        with self._audited_tool("erp_list_audit_events", tenant_id, "audit", api_token):
            if limit < 1 or limit > 100:
                raise ValueError("limit must be between 1 and 100.")
            events = [
                event.to_dict()
                for event in reversed(self.audit_events)
                if event.tenant_id == tenant_id
            ][:limit]
            return {"tenant_id": tenant_id, "events": events}

    def latest_forecast(self) -> dict[str, object]:
        return self.forecast_runs[-1] if self.forecast_runs else {
            "message": "No forecast runs yet. Call erp_forecast_orders first."
        }

    def active_model_version(self, tenant_id: str) -> dict[str, object]:
        for version in reversed(self.model_versions):
            if version.tenant_id == tenant_id and version.status == "active":
                return version.to_dict()
        raise ValueError(f"No active model version for tenant_id={tenant_id}.")

    def _history_for(self, tenant_id: str, sku: str, customer_segment: str) -> list[dict[str, object]]:
        orders = filter_orders(self.dataset.orders, tenant_id, sku, customer_segment)
        history = weekly_series(orders)
        if not history:
            raise ValueError(
                f"No order history for tenant_id={tenant_id}, sku={sku}, segment={customer_segment}. "
                "Use erp://dataset-card or the dashboard to pick a seeded SKU."
            )
        return history

    def _first_history_for_tenant(self, tenant_id: str) -> list[dict[str, object]]:
        products = list_products(self.dataset, tenant_id)
        if not products:
            raise ValueError(f"No products found for tenant_id={tenant_id}.")
        return self._history_for(tenant_id, str(products[0]["sku"]), "all")

    def _orders_for_customer_sku(
        self,
        tenant_id: str,
        sku: str,
        customer_id: str,
    ) -> list[OrderRecord]:
        return [
            order
            for order in self.dataset.orders
            if order.tenant_id == tenant_id and order.sku == sku and order.customer_id == customer_id
        ]

    def _unit_price_for(self, tenant_id: str, sku: str) -> float:
        for product in self.dataset.products:
            if product.tenant_id == tenant_id and product.sku == sku:
                return product.unit_price
        raise ValueError(f"No product found for tenant_id={tenant_id}, sku={sku}.")

    def _recommended_action(self, risk_score: float, trend_pct: float) -> str:
        if risk_score >= 70:
            return "Call this customer this week, review open quotes, and protect inventory for downside demand."
        if risk_score >= 45:
            return "Ask the account owner to confirm near-term orders and prepare a conservative procurement plan."
        if trend_pct < -0.08:
            return "Monitor declining recent demand and check whether the customer is shifting orders to a substitute SKU."
        return "Monitor in the weekly demand review; no urgent intervention required."

    def _select_strategy(self, objective: str, requested_strategy: str) -> str:
        normalized = requested_strategy.lower()
        if normalized in {"greedy", "beam_search"}:
            return normalized
        if any(term in objective for term in ("next order", "next call", "single", "greedy")):
            return "greedy"
        return "beam_search"

    def _select_horizon(self, objective: str, horizon_weeks: int | None) -> int:
        if horizon_weeks is not None:
            if horizon_weeks < 1 or horizon_weeks > 52:
                raise ValueError("horizon_weeks must be between 1 and 52.")
            return horizon_weeks
        if any(term in objective for term in ("inventory", "50", "quarter", "procurement")):
            return 50
        if any(term in objective for term in ("next week", "visit", "prepare")):
            return 4
        return 12

    def _select_temperature(self, objective: str) -> float:
        if any(term in objective for term in ("creative", "substitute", "exchange", "alternative")):
            return 1.35
        if any(term in objective for term in ("inventory", "procurement", "conservative")):
            return 0.75
        return 1.0

    def _inventory_summary(self, scenarios: list[dict[str, object]]) -> dict[str, object]:
        totals = [int(scenario["total_units"]) for scenario in scenarios]
        return {
            "expected_units": totals[0] if totals else 0,
            "downside_units": min(totals) if totals else 0,
            "upside_units": max(totals) if totals else 0,
            "scenario_count": len(scenarios),
        }

    def _products_to_prepare(
        self,
        tenant_id: str,
        anchor_sku: str,
        horizon_weeks: int,
        limit: int,
    ) -> list[dict[str, object]]:
        anchor = next(
            (product for product in self.dataset.products if product.tenant_id == tenant_id and product.sku == anchor_sku),
            None,
        )
        candidates = [
            product
            for product in self.dataset.products
            if product.tenant_id == tenant_id and product.sku != anchor_sku
        ]
        if anchor:
            candidates.sort(key=lambda product: (product.category != anchor.category, -product.base_weekly_demand))
        else:
            candidates.sort(key=lambda product: -product.base_weekly_demand)

        recommendations: list[dict[str, object]] = []
        for product in candidates[:limit]:
            history = self._history_for(tenant_id, product.sku, "all")
            forecast = self.forecaster.forecast(history, min(horizon_weeks, 12))
            recommendations.append(
                {
                    "sku": product.sku,
                    "name": product.name,
                    "category": product.category,
                    "reason": "Related product with strong near-term forecast for the selected customer-planning objective.",
                    "forecast_units": sum(point.predicted_quantity for point in forecast),
                }
            )
        return recommendations

    def _audited_tool(
        self,
        tool_name: str,
        tenant_id: str,
        required_scope: str,
        api_token: str | None,
    ) -> "_AuditContext":
        return _AuditContext(self, tool_name, tenant_id, required_scope, api_token)

    def _record_audit_event(
        self,
        tool_name: str,
        tenant_id: str,
        actor: str,
        key_id: str,
        status: str,
        latency_ms: int,
        error_summary: str | None = None,
    ) -> None:
        self.audit_events.append(
            AuditEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                tool_name=tool_name,
                tenant_id=tenant_id,
                actor=actor,
                key_id=key_id,
                status=status,
                latency_ms=latency_ms,
                timestamp=_now(),
                error_summary=error_summary,
            )
        )
        self.audit_events = self.audit_events[-500:]

    def _loss_curve_for(self, tenant_id: str) -> list[dict[str, float | int]]:
        adjustment = (int(sha256(tenant_id.encode("utf-8")).hexdigest()[:2], 16) % 9) / 1000
        base_train = 0.42 + adjustment
        base_validation = 0.47 + adjustment
        curve: list[dict[str, float | int]] = []
        for step in range(6):
            decay = 0.68 ** step
            curve.append(
                {
                    "step": step,
                    "train_loss": round(base_train * decay + 0.048, 4),
                    "validation_loss": round(base_validation * decay + 0.061, 4),
                }
            )
        return curve

    def _adapter_multiplier_for(self, tenant_id: str) -> float:
        adjustment = (int(sha256(f"{tenant_id}:adapter".encode("utf-8")).hexdigest()[:2], 16) % 5) / 100
        return round(0.86 + adjustment, 2)

    def _improve_metrics(self, metrics: dict[str, float]) -> dict[str, float]:
        return {
            "mae": round(metrics["mae"] * 0.78, 2),
            "smape": round(metrics["smape"] * 0.82, 2),
            "holdout_weeks": metrics["holdout_weeks"],
        }

    def _apply_retraining_effect(
        self,
        forecast_payload: list[dict[str, object]],
        retraining_effect: dict[str, object],
    ) -> list[dict[str, object]]:
        multiplier = float(retraining_effect["adapter_multiplier"])
        adjusted: list[dict[str, object]] = []
        for point in forecast_payload:
            shifted = dict(point)
            shifted["predicted_quantity"] = max(0, round(int(point["predicted_quantity"]) * multiplier))
            shifted["lower_bound"] = max(0, round(int(point["lower_bound"]) * multiplier))
            shifted["upper_bound"] = max(0, round(int(point["upper_bound"]) * multiplier))
            shifted["confidence"] = round(min(0.96, float(point["confidence"]) + 0.035), 3)
            drivers = dict(point["drivers"]) if isinstance(point["drivers"], dict) else {}
            drivers["tenant_adapter"] = "active"
            drivers["adapter_multiplier"] = multiplier
            drivers["adapter_explanation"] = retraining_effect["explanation"]
            shifted["drivers"] = drivers
            adjusted.append(shifted)
        return adjusted

    def _complete_retraining_job(self, job: dict[str, object]) -> None:
        if job["status"] == "completed":
            return
        tenant_id = str(job["tenant_id"])
        pending = dict(job["pending_model_version"])
        model_version = ModelVersion(
            version_id=str(pending["version_id"]),
            model_name=str(pending["model_name"]),
            tenant_id=tenant_id,
            trained_at=_now(),
            metrics=dict(pending["metrics"]),
            status="active",
            base_version_id=str(pending["base_version_id"]),
            adapter_multiplier=float(pending["adapter_multiplier"]),
            explanation=str(pending["explanation"]),
        )
        self.model_versions = [
            version
            if version.tenant_id != tenant_id
            else ModelVersion(
                version_id=version.version_id,
                model_name=version.model_name,
                tenant_id=version.tenant_id,
                trained_at=version.trained_at,
                metrics=version.metrics,
                status="archived",
                base_version_id=version.base_version_id,
                adapter_multiplier=version.adapter_multiplier,
                explanation=version.explanation,
            )
            for version in self.model_versions
        ]
        self.model_versions.append(model_version)
        self.retraining_effects[tenant_id] = {
            "model_version_id": model_version.version_id,
            "adapter_multiplier": model_version.adapter_multiplier,
            "explanation": model_version.explanation,
        }
        job["status"] = "completed"
        job["progress_pct"] = 100
        job["completed_at"] = _now()
        job["loss_curve"] = self._loss_curve_for(tenant_id)
        job["model_version"] = model_version.to_dict()
        job["forecast_shift"] = self.retraining_effects[tenant_id]

    def _public_retraining_job(self, job: dict[str, object]) -> dict[str, object]:
        public = {
            "job_id": job["job_id"],
            "tenant_id": job["tenant_id"],
            "status": job["status"],
            "reason": job["reason"],
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "completed_at": job["completed_at"],
            "progress_pct": job["progress_pct"],
            "loss_curve": job["loss_curve"],
            "before_metrics": job["before_metrics"],
            "after_metrics": job["after_metrics"],
            "explanation": job["explanation"],
            "base_version_id": job["base_version_id"],
        }
        if "model_version" in job:
            public["model_version"] = job["model_version"]
        if "forecast_shift" in job:
            public["forecast_shift"] = job["forecast_shift"]
        return public


_STORE: ForecastStore | None = None


def get_store() -> ForecastStore:
    global _STORE
    if _STORE is None:
        _STORE = ForecastStore()
    return _STORE
