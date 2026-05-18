from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from math import exp, log
from statistics import mean
from typing import Sequence


@dataclass(frozen=True)
class ForecastPoint:
    week: str
    predicted_quantity: int
    lower_bound: int
    upper_bound: int
    confidence: float
    drivers: dict[str, float | str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BeamScenario:
    rank: int
    probability: float
    total_units: int
    quantities: tuple[int, ...]
    weeks: tuple[str, ...]
    label: str
    explanation: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _parse_week(value: str) -> date:
    return date.fromisoformat(value)


def _future_weeks(last_week: str, horizon_weeks: int) -> list[str]:
    start = _parse_week(last_week)
    return [(start + timedelta(days=7 * step)).isoformat() for step in range(1, horizon_weeks + 1)]


def _safe_mean(values: Sequence[float], default: float = 0.0) -> float:
    return mean(values) if values else default


def _softmax(scores: Sequence[float]) -> list[float]:
    if not scores:
        return []
    max_score = max(scores)
    exps = [exp(score - max_score) for score in scores]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


class MiniTransformerForecaster:
    """Small causal attention forecaster with autoregressive and beam-search decoding.

    This intentionally stays dependency-light for the hackathon demo. It models the
    Transformer idea that recent demand tokens attend to earlier demand tokens,
    then decodes future demand autoregressively. The Docker image can swap this
    class for a PyTorch model later without changing MCP tool contracts.
    """

    def __init__(self, context_length: int = 24) -> None:
        self.context_length = context_length
        self.version = "mini-transformer-v1"

    def forecast(
        self,
        history: Sequence[dict[str, object]],
        horizon_weeks: int,
    ) -> list[ForecastPoint]:
        self._validate_history(history, horizon_weeks)
        weeks = _future_weeks(str(history[-1]["week"]), horizon_weeks)
        quantities = [int(item["quantity"]) for item in history]
        generated: list[int] = []
        points: list[ForecastPoint] = []

        for step, week in enumerate(weeks, start=1):
            prediction, drivers = self._predict_next(quantities + generated, step)
            spread = max(8, round(prediction * (0.13 + min(step, 12) * 0.012)))
            confidence = round(max(0.58, 0.91 - step * 0.018), 3)
            point = ForecastPoint(
                week=week,
                predicted_quantity=max(0, round(prediction)),
                lower_bound=max(0, round(prediction - spread)),
                upper_bound=max(0, round(prediction + spread)),
                confidence=confidence,
                drivers=drivers,
            )
            generated.append(point.predicted_quantity)
            points.append(point)
        return points

    def beam_search(
        self,
        history: Sequence[dict[str, object]],
        horizon_weeks: int,
        beam_width: int = 4,
        temperature: float = 1.0,
    ) -> list[BeamScenario]:
        self._validate_history(history, horizon_weeks)
        if not 1 <= beam_width <= 8:
            raise ValueError("beam_width must be between 1 and 8. Try 3 or 4 for a concise demo.")
        if not 0.1 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0.1 and 2.0.")

        base_quantities = [int(item["quantity"]) for item in history]
        weeks = _future_weeks(str(history[-1]["week"]), horizon_weeks)
        beams: list[tuple[list[int], float, list[str]]] = [([], 0.0, [])]

        for step in range(1, horizon_weeks + 1):
            candidates: list[tuple[list[int], float, list[str]]] = []
            for sequence, score, labels in beams:
                expected, _drivers = self._predict_next(base_quantities + sequence, step)
                variants = (
                    ("base demand", expected, 0.42),
                    ("promotion lift", expected * 1.18, 0.22),
                    ("supplier delay", expected * 0.86, 0.16),
                    ("enterprise pull-forward", expected * 1.32, 0.12),
                    ("stockout drag", expected * 0.64, 0.08),
                )
                adjusted_probabilities = self._temperature_adjusted_probabilities(
                    [probability for _label, _value, probability in variants],
                    temperature,
                )
                for (label, value, _probability), adjusted_probability in zip(variants, adjusted_probabilities):
                    next_quantity = max(0, round(value))
                    candidates.append(
                        (
                            [*sequence, next_quantity],
                            score + log(max(adjusted_probability, 1e-9)),
                            [*labels, label],
                        )
                    )
            beams = sorted(candidates, key=lambda item: item[1], reverse=True)[:beam_width]

        probabilities = _softmax([score for _sequence, score, _labels in beams])
        scenarios: list[BeamScenario] = []
        for rank, ((sequence, _score, labels), probability) in enumerate(zip(beams, probabilities), start=1):
            label = self._summarize_labels(labels)
            scenarios.append(
                BeamScenario(
                    rank=rank,
                    probability=round(probability, 3),
                    total_units=sum(sequence),
                    quantities=tuple(sequence),
                    weeks=tuple(weeks),
                    label=label,
                    explanation=(
                        f"{label}; decoded with beam_width={beam_width}, temperature={temperature}, "
                        f"and causal demand attention over the latest {self.context_length} weeks."
                    ),
                )
            )
        return scenarios

    def evaluate_backtest(self, history: Sequence[dict[str, object]], holdout_weeks: int = 8) -> dict[str, float]:
        if len(history) <= holdout_weeks + 12:
            raise ValueError("Need at least 20 weekly points to run backtest metrics.")
        train = history[:-holdout_weeks]
        actual = [int(item["quantity"]) for item in history[-holdout_weeks:]]
        predicted = [point.predicted_quantity for point in self.forecast(train, holdout_weeks)]
        absolute_errors = [abs(a - p) for a, p in zip(actual, predicted)]
        smape_terms = [
            0.0 if a == 0 and p == 0 else abs(a - p) / ((abs(a) + abs(p)) / 2)
            for a, p in zip(actual, predicted)
        ]
        return {
            "mae": round(_safe_mean(absolute_errors), 2),
            "smape": round(_safe_mean(smape_terms) * 100, 2),
            "holdout_weeks": float(holdout_weeks),
        }

    def _validate_history(self, history: Sequence[dict[str, object]], horizon_weeks: int) -> None:
        if horizon_weeks < 1 or horizon_weeks > 52:
            raise ValueError("horizon_weeks must be between 1 and 52.")
        if len(history) < 12:
            raise ValueError("Need at least 12 weekly order points. Try a broader customer_segment.")
        for item in history:
            if "week" not in item or "quantity" not in item:
                raise ValueError("Each history item must include week and quantity.")

    def _predict_next(self, quantities: Sequence[int], step: int) -> tuple[float, dict[str, float | str]]:
        context = list(quantities[-self.context_length :])
        last_4 = _safe_mean(context[-4:], default=float(context[-1]))
        last_12 = _safe_mean(context[-12:], default=last_4)
        previous_12 = _safe_mean(context[-24:-12], default=last_12)
        trend = (last_12 - previous_12) / max(1.0, previous_12)
        attention = self._causal_attention(context)
        seasonal = self._seasonal_prior(list(quantities), step)
        expected = (last_4 * 0.36) + (attention * 0.34) + (seasonal * 0.22) + (last_12 * 0.08)
        expected *= 1.0 + max(-0.18, min(0.18, trend * 0.55))
        if step % 13 in (11, 12):
            expected *= 1.05
        drivers = {
            "recent_average": round(last_4, 2),
            "attention_context": round(attention, 2),
            "seasonal_prior": round(seasonal, 2),
            "trend_pct": round(trend * 100, 2),
            "decoder": "autoregressive",
        }
        return max(0.0, expected), drivers

    def _causal_attention(self, context: Sequence[int]) -> float:
        if not context:
            return 0.0
        query = context[-1]
        scores: list[float] = []
        values: list[float] = []
        for offset, value in enumerate(context):
            recency = (offset + 1) / len(context)
            similarity = -abs(query - value) / max(1.0, query + value)
            scores.append(recency + similarity)
            values.append(float(value))
        weights = _softmax(scores)
        return sum(weight * value for weight, value in zip(weights, values))

    def _seasonal_prior(self, quantities: Sequence[int], step: int) -> float:
        if len(quantities) < 52:
            return _safe_mean(quantities[-12:], default=float(quantities[-1]))
        seasonal_indexes = []
        target_index = len(quantities) + step - 1
        for prior in (52, 104):
            index = target_index - prior
            if 0 <= index < len(quantities):
                seasonal_indexes.append(index)
        values = [float(quantities[index]) for index in seasonal_indexes]
        return _safe_mean(values, default=_safe_mean(quantities[-12:], default=float(quantities[-1])))

    def _temperature_adjusted_probabilities(self, probabilities: Sequence[float], temperature: float) -> list[float]:
        adjusted = [probability ** (1.0 / temperature) for probability in probabilities]
        total = sum(adjusted) or 1.0
        return [value / total for value in adjusted]

    def _summarize_labels(self, labels: Sequence[str]) -> str:
        counts: dict[str, int] = {}
        for label in labels:
            counts[label] = counts.get(label, 0) + 1
        return max(counts.items(), key=lambda item: item[1])[0].title()
