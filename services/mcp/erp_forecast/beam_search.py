"""Beam-search handoff for ranked Swiftron basket scenarios."""

from __future__ import annotations

from .real_model import get_default_model


def run_beam(
    client_id: str,
    start_sequence: list[str] | None,
    beam_width: int = 4,
    horizon: int = 16,
    temperature: float = 1.0,
) -> list[dict[str, object]]:
    """Return ranked scenario trajectories for Lane A's `predict_scenarios` tool.

    Example:
        `run_beam("nexus_lab_solutions", [], beam_width=2, horizon=3)` returns
        `[{"rank": 1, "joint_log_prob": -1.23, "tokens": [...], "time_deltas": [...]}]`.
    """
    return get_default_model().run_beam(
        client_id=client_id,
        start_sequence=start_sequence,
        beam_width=beam_width,
        horizon=horizon,
        temperature=temperature,
    )
