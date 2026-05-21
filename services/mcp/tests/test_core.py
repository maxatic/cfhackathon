import os
import unittest
from math import log
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


class ControlledBeamModel(RealSequenceModel):
    """Deterministic decoder proving beam search keeps competing paths."""

    def __init__(self) -> None:
        """Skip artifact loading for a pure decoder-control test."""

    def _dataset_for(self, client_id: str) -> object:
        """Return a fake dataset for the demo client.

        Example:
            `_dataset_for("nexus_lab_solutions")` returns an object.
        """
        if client_id != "nexus_lab_solutions":
            raise ValueError(f"Unknown client_id={client_id}.")
        return object()

    def _resolve_start_tokens(
        self,
        dataset: object,
        start_sequence: list[str] | None,
        seed: int,
    ) -> tuple[list[str], list[str]]:
        """Return a fixed context for deterministic beam comparison.

        Example:
            `_resolve_start_tokens(object(), None, 42)` returns `(["history"], [])`.
        """
        return ["history"], []

    def _prepare_decoder(self, dataset: object, seed: int, sensor_tokens: list[str] | None) -> object:
        """Return a fake decoder state.

        Example:
            `_prepare_decoder(object(), 42, None)` returns an object.
        """
        return object()

    def _time_candidates(self, state: object, tokens: list[str], limit: int) -> list[tuple[str, float]]:
        """Return a greedy time token and a lower-probability alternative.

        Example:
            `_time_candidates(object(), ["history"], 1)` returns the greedy token only.
        """
        return [
            ("<dt_greedy>", log(0.7)),
            ("<dt_alt>", log(0.3)),
        ][:limit]

    def _product_candidates(
        self,
        state: object,
        tokens: list[str],
        used_global_indices: set[int],
        temperature: float,
        limit: int,
    ) -> list[tuple[str, int | None, float]]:
        """Return branch-specific product log-probs for beam proof.

        Example:
            a context containing `"<dt_alt>"` returns the alternate branch candidates.
        """
        time_token = next(token for token in tokens if token.startswith("<dt_"))
        candidates_by_time = {
            "<dt_greedy>": [
                ("greedy_refill", 101, log(0.5)),
                ("slow_refill", 102, log(0.2)),
            ],
            "<dt_alt>": [
                ("alternate_refill", 201, log(0.99)),
                ("alternate_tail", 202, log(0.01)),
            ],
        }
        candidates = candidates_by_time[time_token]
        return [candidate for candidate in candidates if candidate[1] not in used_global_indices][:limit]


class SensorAwareFakeModel:
    """Fake model that exposes a distribution shift from sensor tokens."""

    def list_clients(self) -> list[str]:
        """Return the single demo client.

        Example:
            `list_clients()` returns `["nexus_lab_solutions"]`.
        """
        return ["nexus_lab_solutions"]

    def vocab_for_client(self, client_id: str) -> list[str]:
        """Return two valid tokens for sensor tests.

        Example:
            `vocab_for_client("nexus_lab_solutions")` returns two fake product tokens.
        """
        if client_id != "nexus_lab_solutions":
            raise ValueError(f"Unknown client_id={client_id}.")
        return ["chem_signal", "bio_signal"]

    def predict_basket(
        self,
        client_id: str,
        start_sequence: list[str] | None,
        max_generate: int = 32,
        top_k: int = 5,
        temperature: float = 1.0,
        seed: int | None = None,
        sensor_tokens: list[str] | None = None,
    ) -> dict[str, object]:
        """Return a distribution determined by the sensor tokens.

        Example:
            `predict_basket("nexus_lab_solutions", [], sensor_tokens=["bio_signal"])`
            returns a payload where the biology probability is higher.
        """
        if sensor_tokens == ["bio_signal"]:
            distribution = {"chem_signal": 0.2, "bio_signal": 0.8}
            generated = ["bio_signal"]
        else:
            distribution = {"chem_signal": 0.85, "bio_signal": 0.15}
            generated = ["chem_signal"]
        return {
            "client_id": client_id,
            "start_sequence": start_sequence or [],
            "generated_tokens": generated,
            "generated_times": [0],
            "token_distribution": distribution,
            "model_version": "fake",
            "decoder_config": {
                "strategy": "sensor_profile",
                "top_k": top_k,
                "temperature": temperature,
                "max_generate": max_generate,
                "seed": seed,
            },
        }


def _product_tokens(vocab: list[str], count: int) -> list[str]:
    """Return non-time tokens without logging protected vocabulary.

    Example:
        `_product_tokens(["<dt_1w>", "a", "b"], 2)` returns `["a", "b"]`.
    """
    tokens: list[str] = []
    for token in vocab:
        token_text = str(token)
        if token_text not in {"<unk>", "<eos>"} and not token_text.startswith("<dt_"):
            tokens.append(token_text)
            if len(tokens) == count:
                break
    return tokens


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


class BeamSearchProofTests(unittest.TestCase):
    def test_beam_search_keeps_alternatives_and_sums_log_probs(self) -> None:
        """A wider beam should keep non-greedy paths and sum per-step log-probs."""
        model = ControlledBeamModel()

        greedy = model.run_beam("nexus_lab_solutions", None, beam_width=1, horizon=2)
        wide = model.run_beam("nexus_lab_solutions", None, beam_width=4, horizon=2)

        self.assertEqual(greedy[0]["tokens"], ["<dt_greedy>", "greedy_refill"])
        self.assertTrue(any(scenario["tokens"][0] != greedy[0]["tokens"][0] for scenario in wide))

        scores = [float(scenario["joint_log_prob"]) for scenario in wide]
        self.assertEqual(scores, sorted(scores, reverse=True))

        expected_scores = {
            ("<dt_greedy>", "greedy_refill"): log(0.7) + log(0.5),
            ("<dt_alt>", "alternate_refill"): log(0.3) + log(0.99),
            ("<dt_greedy>", "slow_refill"): log(0.7) + log(0.2),
            ("<dt_alt>", "alternate_tail"): log(0.3) + log(0.01),
        }
        for scenario in wide:
            key = tuple(scenario["tokens"])
            self.assertAlmostEqual(float(scenario["joint_log_prob"]), expected_scores[key], delta=1e-4)


class SensorExplainabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        """Clear cached sessions before each sensor test."""
        sensor._SESSIONS.clear()

    def test_different_sensor_tokens_change_distribution_for_same_seed(self) -> None:
        """Two sensor token sets should produce different output distributions."""
        fake_model = SensorAwareFakeModel()

        with patch("erp_forecast.sensor.get_default_model", return_value=fake_model):
            chem_session = sensor.apply_sensor("nexus_lab_solutions", ["chem_signal"])
            bio_session = sensor.apply_sensor("nexus_lab_solutions", ["bio_signal"])
            chem_result = sensor.predict_with_session(chem_session, [], max_generate=2, seed=9)
            bio_result = sensor.predict_with_session(bio_session, [], max_generate=2, seed=9)

        self.assertEqual(chem_result["decoder_config"]["seed"], bio_result["decoder_config"]["seed"])
        self.assertNotEqual(chem_result["token_distribution"], bio_result["token_distribution"])
        self.assertNotEqual(chem_result["generated_tokens"], bio_result["generated_tokens"])

    def test_sensor_rejects_tokens_outside_client_vocab(self) -> None:
        """Sensor sessions should not silently accept tokens the model ignores."""
        with patch("erp_forecast.sensor.get_default_model", return_value=SensorAwareFakeModel()):
            with self.assertRaisesRegex(ValueError, "vocabulary"):
                sensor.apply_sensor("nexus_lab_solutions", ["missing_token"])


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
        valid_tokens = _product_tokens(self.model.vocab_for_client("nexus_lab_solutions"), 1)
        if not valid_tokens:
            raise unittest.SkipTest("No product token is available for sensor validation.")

        with patch("erp_forecast.sensor.get_default_model", return_value=self.model):
            session_id = sensor.apply_sensor("nexus_lab_solutions", valid_tokens)
            result = sensor.predict_with_session(session_id, None, max_generate=2, seed=11)

        self.assertEqual(result["client_id"], "nexus_lab_solutions")
        self.assertEqual(result["decoder_config"]["strategy"], "sensor_profile")

    def test_sensor_tokens_change_real_candidate_distribution(self) -> None:
        """Real sensor token sets should change next-product probabilities."""
        valid_tokens = _product_tokens(self.model.vocab_for_client("nexus_lab_solutions"), 2)
        if len(valid_tokens) < 2:
            raise unittest.SkipTest("Two product tokens are required for sensor distribution validation.")

        first = self.model._sensor_distribution_probe(
            "nexus_lab_solutions",
            None,
            [valid_tokens[0]],
            top_k=8,
            seed=13,
        )
        second = self.model._sensor_distribution_probe(
            "nexus_lab_solutions",
            None,
            [valid_tokens[1]],
            top_k=8,
            seed=13,
        )

        first_distribution = {str(item["token"]): float(item["probability"]) for item in first}
        second_distribution = {str(item["token"]): float(item["probability"]) for item in second}
        compared_tokens = set(first_distribution) | set(second_distribution)
        total_delta = sum(
            abs(first_distribution.get(token, 0.0) - second_distribution.get(token, 0.0))
            for token in compared_tokens
        )
        self.assertGreater(total_delta, 1e-9)


class _FakeBeamModel:
    """Fake model that records the horizon it was asked to decode."""

    def __init__(self) -> None:
        """Track the most recent beam horizon for assertions."""
        self.last_horizon: int | None = None

    def run_beam(
        self,
        client_id: str,
        start_sequence: list[str] | None,
        beam_width: int,
        horizon: int,
        temperature: float,
    ) -> list[dict[str, object]]:
        """Return a single trivial trajectory and remember the horizon.

        Example:
            `run_beam("nexus_lab_solutions", None, 4, 6, 1.0)` returns one trajectory.
        """
        self.last_horizon = horizon
        tokens = ["<dt_1w>", "productalpha"][:max(2, horizon)]
        return [
            {
                "rank": 1,
                "joint_log_prob": -1.0,
                "tokens": tokens,
                "time_deltas": [7] * len(tokens),
            }
        ]


class BeamHorizonCapTests(unittest.TestCase):
    """Server-level horizon defaults and clamping for beam paths."""

    def test_forecast_plan_default_horizon_is_six(self) -> None:
        """forecast_plan should drop to BEAM_HORIZON_DEFAULT when no hint is passed."""
        from erp_forecast import real_model, server, tool_schemas

        fake = _FakeBeamModel()
        with patch.object(real_model, "get_default_model", return_value=fake):
            payload = server.forecast_plan(
                client_id="nexus_lab_solutions",
                objective_text="compare scenarios for the next basket",
                horizon_hint=None,
            )

        self.assertEqual(payload["chosen_strategy"], "beam_search")
        self.assertEqual(
            payload["payload"]["decoder_config"]["horizon"],
            tool_schemas.BEAM_HORIZON_DEFAULT,
        )
        self.assertEqual(fake.last_horizon, tool_schemas.BEAM_HORIZON_DEFAULT)

    def test_forecast_plan_clamps_excessive_hint(self) -> None:
        """horizon_hint above BEAM_HORIZON_MAX should be clamped, not raised."""
        from erp_forecast import real_model, server, tool_schemas

        fake = _FakeBeamModel()
        with patch.object(real_model, "get_default_model", return_value=fake):
            payload = server.forecast_plan(
                client_id="nexus_lab_solutions",
                objective_text="list alternatives over a long horizon",
                horizon_hint=64,
            )

        self.assertEqual(
            payload["payload"]["decoder_config"]["horizon"],
            tool_schemas.BEAM_HORIZON_MAX,
        )
        self.assertEqual(fake.last_horizon, tool_schemas.BEAM_HORIZON_MAX)

    def test_predict_scenarios_default_horizon_is_six(self) -> None:
        """predict_scenarios with no horizon argument should use BEAM_HORIZON_DEFAULT."""
        from erp_forecast import real_model, server, tool_schemas

        fake = _FakeBeamModel()
        with patch.object(real_model, "get_default_model", return_value=fake):
            payload = server.predict_scenarios(client_id="nexus_lab_solutions")

        self.assertEqual(
            payload["decoder_config"]["horizon"], tool_schemas.BEAM_HORIZON_DEFAULT
        )
        self.assertEqual(fake.last_horizon, tool_schemas.BEAM_HORIZON_DEFAULT)

    def test_predict_scenarios_clamps_caller_horizon(self) -> None:
        """A caller passing horizon=40 should still be clamped to BEAM_HORIZON_MAX."""
        from erp_forecast import real_model, server, tool_schemas

        fake = _FakeBeamModel()
        with patch.object(real_model, "get_default_model", return_value=fake):
            payload = server.predict_scenarios(
                client_id="nexus_lab_solutions",
                horizon=40,
            )

        self.assertEqual(
            payload["decoder_config"]["horizon"], tool_schemas.BEAM_HORIZON_MAX
        )
        self.assertEqual(fake.last_horizon, tool_schemas.BEAM_HORIZON_MAX)


if __name__ == "__main__":
    unittest.main()
