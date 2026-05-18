import unittest

from erp_forecast.data import DEMO_DECLINING_CUSTOMERS, DEMO_RISK_SKU, filter_orders, get_default_dataset, weekly_series
from erp_forecast.jobs import ForecastStore, _customer_ref
from erp_forecast.model import MiniTransformerForecaster
from erp_forecast.privacy import anonymize_orders


class ForecastCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = get_default_dataset()
        self.store = ForecastStore(self.dataset)
        self.tenant_id = "tenant_northstar"
        self.sku = self.store.summary()["products"][self.tenant_id][0]["sku"]

    def test_synthetic_dataset_has_expected_entities(self) -> None:
        summary = self.store.summary()
        self.assertEqual(summary["tenant_count"], 2)
        self.assertEqual(summary["customer_count"], 400)
        self.assertEqual(summary["product_count"], 100)
        self.assertGreater(summary["order_count"], 300_000)
        self.assertGreater(summary["customer_revenue_concentration"]["top_10_share_pct"], 8)
        self.assertEqual(summary["demo_risk_sku"], DEMO_RISK_SKU)
        self.assertEqual(summary["demo_declining_customers"], list(DEMO_DECLINING_CUSTOMERS))
        self.assertGreater(len(summary["top_skus"]), 0)

    def test_forecast_generates_requested_horizon(self) -> None:
        result = self.store.forecast_orders(
            tenant_id=self.tenant_id,
            sku=self.sku,
            horizon_weeks=12,
            api_token="demo_northstar_full",
        )
        self.assertEqual(len(result["forecast"]), 12)
        self.assertIn("metrics", result)
        self.assertGreater(result["forecast"][0]["predicted_quantity"], 0)

    def test_beam_search_returns_ranked_scenarios(self) -> None:
        result = self.store.beam_search_forecast(
            tenant_id=self.tenant_id,
            sku=self.sku,
            horizon_weeks=6,
            beam_width=4,
            temperature=1.2,
            api_token="demo_northstar_full",
        )
        self.assertEqual(len(result["scenarios"]), 4)
        self.assertEqual(result["temperature"], 1.2)
        self.assertEqual(result["scenarios"][0]["rank"], 1)
        self.assertGreaterEqual(result["scenarios"][0]["probability"], result["scenarios"][-1]["probability"])

    def test_adaptive_forecast_plan_selects_customer_visit_workflow(self) -> None:
        result = self.store.adaptive_forecast_plan(
            tenant_id=self.tenant_id,
            sku=DEMO_RISK_SKU,
            objective="I visit this customer next week. What three products should I prepare for?",
            recommendation_count=3,
            api_token="demo_northstar_full",
        )
        self.assertEqual(result["selected_strategy"], "beam_search")
        self.assertEqual(result["decoder_plan"]["horizon_weeks"], 4)
        self.assertIn("customer_risk", result)
        self.assertEqual(len(result["products_to_prepare"]), 3)
        self.assertIn("scenarios", result)

    def test_adaptive_forecast_plan_can_force_greedy(self) -> None:
        result = self.store.adaptive_forecast_plan(
            tenant_id=self.tenant_id,
            sku=self.sku,
            objective="predict the single next order",
            strategy="greedy",
            horizon_weeks=1,
            api_token="demo_northstar_full",
        )
        self.assertEqual(result["selected_strategy"], "greedy")
        self.assertEqual(result["decoder_plan"]["strategy"], "greedy")
        self.assertEqual(len(result["forecast"]["forecast"]), 1)

    def test_rank_at_risk_customers_returns_sorted_customer_refs(self) -> None:
        result = self.store.rank_at_risk_customers(
            tenant_id=self.tenant_id,
            sku=self.sku,
            horizon_weeks=12,
            limit=5,
            api_token="demo_northstar_full",
        )
        ranked = result["ranked_customers"]
        self.assertEqual(len(ranked), 5)
        scores = [customer["risk_score"] for customer in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertTrue(ranked[0]["customer_ref"].startswith("cust_"))
        self.assertIn("current_demand", ranked[0])
        self.assertIn("forecast_demand", ranked[0])
        self.assertIn("downside_scenario", ranked[0])
        self.assertIn("recommended_action", ranked[0])

    def test_declining_demo_customers_rank_as_risky(self) -> None:
        result = self.store.rank_at_risk_customers(
            tenant_id=self.tenant_id,
            sku=DEMO_RISK_SKU,
            horizon_weeks=12,
            limit=5,
            api_token="demo_northstar_full",
        )
        top_refs = [customer["customer_ref"] for customer in result["ranked_customers"][:2]]
        expected_refs = [_customer_ref(customer_id) for customer_id in DEMO_DECLINING_CUSTOMERS]
        self.assertEqual(top_refs, expected_refs)
        for customer in result["ranked_customers"][:2]:
            self.assertGreater(customer["current_demand"]["decline_vs_baseline_pct"], 35)
            self.assertGreater(customer["revenue_at_risk"], 10_000)

    def test_rank_at_risk_customers_rejects_wrong_tenant_token(self) -> None:
        with self.assertRaises(ValueError):
            self.store.rank_at_risk_customers(
                tenant_id=self.tenant_id,
                sku=self.sku,
                horizon_weeks=12,
                limit=3,
                api_token="demo_apex_full",
            )

    def test_api_key_scope_checks_and_audit_events(self) -> None:
        self.store.forecast_orders(
            tenant_id=self.tenant_id,
            sku=self.sku,
            horizon_weeks=4,
            api_token="sk_northstar_forecast_read",
        )
        with self.assertRaises(ValueError):
            self.store.anonymize(
                tenant_id=self.tenant_id,
                sku=self.sku,
                sample_size=2,
                api_token="sk_northstar_forecast_read",
            )
        events = self.store.list_audit_events(
            tenant_id=self.tenant_id,
            limit=5,
            api_token="sk_northstar_forecast_read",
        )["events"]
        self.assertGreaterEqual(len(events), 2)
        self.assertTrue(any(event["tool_name"] == "erp_forecast_orders" and event["status"] == "success" for event in events))
        self.assertTrue(any(event["tool_name"] == "erp_anonymize_orders" and event["status"] == "error" for event in events))
        self.assertEqual(self.store.audit_events[-1].tool_name, "erp_list_audit_events")
        forecast_event = next(event for event in events if event["tool_name"] == "erp_forecast_orders")
        self.assertEqual(forecast_event["actor"], "agent-northstar-viewer")
        self.assertEqual(forecast_event["key_id"], "key_northstar_read")

    def test_anonymization_removes_customer_identity(self) -> None:
        orders = filter_orders(self.dataset.orders, self.tenant_id, self.sku)
        report = anonymize_orders(orders, sample_size=5)
        row = report["sample"][0]
        self.assertIn("customer_ref", row)
        self.assertNotIn("customer_name", row)
        self.assertNotIn("customer_id", row)
        self.assertIn("customer_id", report["fields_hashed"])
        self.assertIn("customer_name", report["detected_sensitive_fields"])
        self.assertEqual(report["row_count"], len(orders))

    def test_anonymization_accepts_raw_rows_and_hashes_deterministically(self) -> None:
        raw_rows = [
            {
                "tenant_id": self.tenant_id,
                "customer_id": "CFO-ACME-001",
                "customer_name": "Acme Components",
                "contact_email": "buyer@acme.example",
                "ship_to_address": "123 Market St",
                "po_number": "PO-4451",
                "segment": "enterprise",
                "region": "North America",
                "sku": DEMO_RISK_SKU,
                "order_date": "2026-05-04",
                "quantity": 44,
                "unit_price": 184.0,
            }
        ]
        first = anonymize_orders(raw_rows, sample_size=1)
        second = anonymize_orders(raw_rows, sample_size=1)
        self.assertEqual(first["sample"][0]["customer_ref"], second["sample"][0]["customer_ref"])
        self.assertIn("ship_to_address", first["fields_scrubbed"])
        self.assertIn("po_number", first["fields_scrubbed"])
        self.assertIn("contact_email", first["fields_hashed"])
        self.assertIn("ship_to_address", first["detected_sensitive_fields"])
        self.assertNotIn("ship_to_address", first["sample"][0])

    def test_retraining_lifecycle_completes_after_polling_and_creates_model(self) -> None:
        before_forecast = self.store.forecast_orders(
            tenant_id=self.tenant_id,
            sku=self.sku,
            horizon_weeks=4,
            api_token="demo_northstar_full",
        )
        job = self.store.trigger_retraining(
            tenant_id=self.tenant_id,
            reason="unit test",
            api_token="demo_northstar_full",
        )
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["progress_pct"], 0)
        self.assertIn("before_metrics", job)
        self.assertIn("after_metrics", job)
        self.assertIn("loss_curve", job)
        self.assertNotIn("model_version", job)

        running = self.store.get_retraining_status(
            tenant_id=self.tenant_id,
            job_id=job["job_id"],
            api_token="demo_northstar_full",
        )
        self.assertEqual(running["status"], "running")
        self.assertGreater(len(running["loss_curve"]), len(job["loss_curve"]))
        self.assertNotIn("model_version", running)

        completed = self.store.get_retraining_status(
            tenant_id=self.tenant_id,
            job_id=job["job_id"],
            api_token="demo_northstar_full",
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["progress_pct"], 100)
        self.assertEqual(completed["job_id"], job["job_id"])
        self.assertIn("model_version", completed)
        self.assertIn("forecast_shift", completed)
        self.assertLess(completed["after_metrics"]["mae"], completed["before_metrics"]["mae"])
        versions = self.store.list_model_versions(self.tenant_id, api_token="demo_northstar_full")
        self.assertTrue(
            any(
                version["version_id"] == completed["model_version"]["version_id"]
                and version["status"] == "active"
                for version in versions["model_versions"]
            )
        )
        after_forecast = self.store.forecast_orders(
            tenant_id=self.tenant_id,
            sku=self.sku,
            horizon_weeks=4,
            api_token="demo_northstar_full",
        )
        self.assertEqual(after_forecast["model_version"], completed["model_version"]["version_id"])
        self.assertLess(
            after_forecast["forecast"][0]["predicted_quantity"],
            before_forecast["forecast"][0]["predicted_quantity"],
        )
        self.assertIn("retraining_effect", after_forecast)

    def test_forecaster_rejects_invalid_beam_width(self) -> None:
        orders = filter_orders(self.dataset.orders, self.tenant_id, self.sku)
        history = weekly_series(orders)
        forecaster = MiniTransformerForecaster()
        with self.assertRaises(ValueError):
            forecaster.beam_search(history, horizon_weeks=3, beam_width=12)
        with self.assertRaises(ValueError):
            forecaster.beam_search(history, horizon_weeks=3, temperature=3.0)


if __name__ == "__main__":
    unittest.main()
