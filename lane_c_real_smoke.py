"""Smoke test for Lane C real_model wrappers against Swiftron's protected bundle.

Run from repo root:
  source services/mcp/.venv/bin/activate
  export REAL_MODEL_ARTIFACT_DIR="/Users/theorkhn/Documents/cfhackathon/artifacts"
  export PYTHONPATH=services/mcp
  python lane_c_real_smoke.py
"""

import os

from erp_forecast.real_model import RealSequenceModel


CLIENT_ID = "nexus_lab_solutions"


def main() -> None:
    artifact_dir = os.environ["REAL_MODEL_ARTIFACT_DIR"]
    model = RealSequenceModel(artifact_dir)

    clients = model.list_clients()
    assert CLIENT_ID in clients, f"{CLIENT_ID} missing from client list"

    first = model.predict_basket(
        CLIENT_ID,
        None,
        max_generate=3,
        top_k=5,
        temperature=1.0,
        seed=7,
    )
    second = model.predict_basket(
        CLIENT_ID,
        None,
        max_generate=3,
        top_k=5,
        temperature=1.0,
        seed=7,
    )

    assert first["client_id"] == CLIENT_ID
    assert first["model_version"] == "swiftron-onnx-v1"
    assert first["generated_tokens"] == second["generated_tokens"]
    assert len(first["generated_tokens"]) == len(first["generated_times"])

    scenarios = model.run_beam(
        CLIENT_ID,
        None,
        beam_width=2,
        horizon=3,
        temperature=1.0,
    )

    assert len(scenarios) == 2
    assert [scenario["rank"] for scenario in scenarios] == [1, 2]
    assert scenarios[0]["joint_log_prob"] >= scenarios[1]["joint_log_prob"]
    assert len(scenarios[0]["tokens"]) == len(scenarios[0]["time_deltas"])

    print("real_model_smoke=ok")
    print(f"client_count={len(clients)}")
    print(f"prediction_token_count={len(first['generated_tokens'])}")
    print(f"scenario_count={len(scenarios)}")


if __name__ == "__main__":
    main()
