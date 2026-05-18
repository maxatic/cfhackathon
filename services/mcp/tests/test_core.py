import os
import unittest
from unittest.mock import patch

from erp_forecast import sensor
from erp_forecast.privacy import anonymize_orders
from erp_forecast.real_model import RealSequenceModel, _time_delta_days
from erp_forecast.tokenize_orders import anonymize_and_tokenize


class FakeModel:
    def vocab_for_client(self, client_id: str) -> list[str]:
        """Return a small fake vocabulary for tokenization-only tests."""
        if client_id != "nexus_lab_solutions":
            raise ValueError(f"Unknown client_id={client_id}.")
        return ["<unk>", "<dt_1w>", "productalpha", "benchglove"]


class PrivacyAndTokenizationTests(unittest.TestCase):
    def test_anonymization_removes_customer_identity(self) -> None:
        """Anonymization should remove direct identifiers from samples."""
        raw_rows = [
            {
                "customer_id": "CUST-001",
                "customer_name": "Example Buyer",
                "contact_email": "buyer@example.test",
                "ship_to_address": "123 Market St",
                "po_number": "PO-4451",
                "product_sku": "productalpha",
                "order_date": "2026-05-01",
                "quantity": 3,
                "unit_price": 42.0,
            }
        ]

        report = anonymize_orders(raw_rows, sample_size=1)

        self.assertEqual(report["row_count"], 1)
        self.assertIn("customer_name", report["fields_hashed"])
        self.assertIn("ship_to_address", report["fields_scrubbed"])
        self.assertNotIn("customer_name", report["sample"][0])
        self.assertIn("customer_ref", report["sample"][0])

    def test_anonymize_and_tokenize_maps_rows_to_vocab(self) -> None:
        """Tokenization should sort rows by date and map product labels to vocab."""
        raw_rows = [
            {
                "row_id": "input-2",
                "product_sku": "bench glove",
                "customer_name": "Example Buyer",
                "order_date": "2026-05-08",
            },
            {
                "row_id": "input-1",
                "product_sku": "Product Alpha",
                "ship_to_address": "123 Market St",
                "order_date": "2026-05-01",
            },
        ]

        with patch("erp_forecast.tokenize_orders.get_default_model", return_value=FakeModel()):
            result = anonymize_and_tokenize(raw_rows, "nexus_lab_solutions")

        self.assertEqual(result["client_id"], "nexus_lab_solutions")
        self.assertEqual(result["tokenized"], ["productalpha", "benchglove"])
        self.assertEqual(result["time_deltas"], [0, 7])
        self.assertEqual(result["audit_report"]["row_count"], 2)
        self.assertEqual([row["row_id"] for row in result["rows"]], ["input-1", "input-2"])

    def test_time_delta_parser_handles_model_tokens(self) -> None:
        """Time tokens should become day deltas and product tokens should become zero."""
        self.assertEqual(_time_delta_days("<dt_1w>"), 7)
        self.assertEqual(_time_delta_days("<dt_3d>"), 3)
        self.assertEqual(_time_delta_days("productalpha"), 0)


class RealModelContractTests(unittest.TestCase):
    def test_generation_validation_runs_before_artifact_loading(self) -> None:
        """Invalid generation parameters should fail before artifact access."""
        model = RealSequenceModel("/definitely/missing/artifacts")

        with self.assertRaisesRegex(ValueError, "max_generate"):
            model.predict_basket("nexus_lab_solutions", [], max_generate=0)

    def test_missing_artifacts_error_is_descriptive(self) -> None:
        """Missing artifacts should tell the agent which env var to configure."""
        model = RealSequenceModel("/definitely/missing/artifacts")

        with self.assertRaisesRegex(ValueError, "REAL_MODEL_ARTIFACT_DIR"):
            model.list_clients()

    def test_sensor_unknown_session_fails_cleanly(self) -> None:
        """Unknown sensor sessions should return a recoverable error."""
        with self.assertRaisesRegex(ValueError, "Unknown session_id"):
            sensor.predict_with_session("session_missing", [], max_generate=2)


class RealArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Skip artifact tests when the protected runtime is unavailable."""
        artifact_dir = os.getenv("REAL_MODEL_ARTIFACT_DIR")
        if not artifact_dir:
            raise unittest.SkipTest("REAL_MODEL_ARTIFACT_DIR is not set.")
        cls.model = RealSequenceModel(artifact_dir)
        try:
            clients = cls.model.list_clients()
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise unittest.SkipTest(f"Protected runtime unavailable: {exc}") from exc
        if "nexus_lab_solutions" not in clients:
            raise unittest.SkipTest("nexus_lab_solutions is not present in the mounted dataset.")

    def test_predict_basket_shape_and_seed_reproducibility(self) -> None:
        """Real prediction should return the handoff shape and repeat for a fixed seed."""
        first = self.model.predict_basket(
            "nexus_lab_solutions",
            None,
            max_generate=3,
            top_k=5,
            temperature=1.0,
            seed=7,
        )
        second = self.model.predict_basket(
            "nexus_lab_solutions",
            None,
            max_generate=3,
            top_k=5,
            temperature=1.0,
            seed=7,
        )

        self.assertEqual(first["client_id"], "nexus_lab_solutions")
        self.assertEqual(first["model_version"], "swiftron-onnx-v1")
        self.assertEqual(first["generated_tokens"], second["generated_tokens"])
        self.assertEqual(len(first["generated_tokens"]), len(first["generated_times"]))

    def test_unknown_client_errors(self) -> None:
        """Unknown real clients should produce a descriptive error."""
        with self.assertRaisesRegex(ValueError, "Unknown client_id"):
            self.model.predict_basket("missing_client", None, max_generate=2)

    def test_beam_search_returns_ranked_outputs(self) -> None:
        """Real beam search should return ranked trajectories with aligned deltas."""
        scenarios = self.model.run_beam(
            "nexus_lab_solutions",
            None,
            beam_width=2,
            horizon=3,
            temperature=1.0,
        )

        self.assertEqual(len(scenarios), 2)
        self.assertEqual([scenario["rank"] for scenario in scenarios], [1, 2])
        self.assertGreaterEqual(scenarios[0]["joint_log_prob"], scenarios[1]["joint_log_prob"])
        self.assertEqual(len(scenarios[0]["tokens"]), len(scenarios[0]["time_deltas"]))

    def test_sensor_session_prediction_shape(self) -> None:
        """Sensor prediction should return the same basket shape with sensor strategy."""
        sensor._SESSIONS.clear()

        with patch("erp_forecast.sensor.get_default_model", return_value=self.model):
            session_id = sensor.apply_sensor("nexus_lab_solutions", ["demo_added_token"])
            result = sensor.predict_with_session(session_id, None, max_generate=2, seed=11)

        self.assertEqual(result["client_id"], "nexus_lab_solutions")
        self.assertEqual(result["decoder_config"]["strategy"], "sensor_profile")


if __name__ == "__main__":
    unittest.main()
