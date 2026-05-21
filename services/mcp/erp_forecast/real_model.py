"""Adapter and decoder helpers for Swiftron's protected ONNX model."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from os import environ, getenv
from pathlib import Path
from random import Random
from shutil import copy2
from sys import platform
from typing import Any, Sequence


MODEL_VERSION = "swiftron-onnx-v1"
_DEFAULT_MODEL: RealSequenceModel | None = None


@dataclass(frozen=True)
class RealSequencePrediction:
    """Legacy REST response wrapper for direct model calls."""

    client_id: str
    start_sequence: str
    generated_sequence: str
    max_generate: int
    temperature: float
    top_k: int
    seed: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe payload.

        Example:
            `prediction.to_dict()["tokens"]` returns the generated token list.
        """
        return {
            "client_id": self.client_id,
            "start_sequence": self.start_sequence,
            "generated_sequence": self.generated_sequence,
            "tokens": self.generated_sequence.split(),
            "max_generate": self.max_generate,
            "temperature": self.temperature,
            "top_k": self.top_k,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class _DecoderState:
    """Prepared arrays reused by autoregressive and beam decoders."""

    dataset: Any
    session: Any
    word_to_int: dict[str, int]
    vocab: Sequence[str]
    raw_vectors: Any
    time_tokens: Sequence[str]
    product_indices: Any
    aligned_candidates: Any
    sensor_input: Any
    dummy_catalog: Any
    vector_size: int


class RealSequenceModel:
    """Thin adapter around the NDA-provided ONNX model and public dataset class."""

    def __init__(
        self,
        artifact_dir: str,
        model_filename: str = "landing_page_model.onnx",
        dataset_filename: str = "multi_client_dataset.joblib",
    ) -> None:
        """Create a lazy model wrapper.

        Example:
            `RealSequenceModel("/safe/path/to/artifacts").list_clients()` returns client ids.
        """
        self.artifact_dir = Path(artifact_dir).expanduser().resolve()
        self.model_path = self.artifact_dir / model_filename
        self.dataset_path = self.artifact_dir / dataset_filename
        self.vector_size = 128
        self.max_catalog_size = 256
        self.max_seq_len = 512
        self.current_seq_len = self.max_seq_len - 1
        self._session: Any | None = None
        self._dataset_map: dict[str, Any] | None = None
        self._import_dir: Path | None = None

    def predict(
        self,
        client_id: str,
        start_sequence: str | None = None,
        max_generate: int = 30,
        temperature: float = 1.0,
        top_k: int = 30,
        seed: int = 42,
    ) -> RealSequencePrediction:
        """Run direct top-k autoregressive prediction for the legacy endpoint.

        Example:
            `predict("nexus_lab_solutions", max_generate=2).to_dict()` returns generated tokens.
        """
        self._validate_generation_args(max_generate=max_generate, top_k=top_k, temperature=temperature)
        dataset = self._dataset_for(client_id)
        start_tokens, _public_start = self._resolve_start_tokens(dataset, _split_sequence(start_sequence), seed)
        generated = self._generate_tokens(
            dataset=dataset,
            start_tokens=start_tokens,
            max_generate=max_generate,
            temperature=temperature,
            top_k=top_k,
            seed=seed,
            sensor_tokens=None,
        )
        return RealSequencePrediction(
            client_id=client_id,
            start_sequence=" ".join(start_tokens),
            generated_sequence=" ".join(generated),
            max_generate=max_generate,
            temperature=temperature,
            top_k=top_k,
            seed=seed,
        )

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
        """Return the handoff payload for the `predict_next_basket` tool.

        Example:
            `predict_basket("nexus_lab_solutions", [], max_generate=2)` returns
            `{"client_id": "nexus_lab_solutions", "generated_tokens": [...], ...}`.
        """
        actual_seed = _coerce_seed(seed)
        self._validate_generation_args(max_generate=max_generate, top_k=top_k, temperature=temperature)
        dataset = self._dataset_for(client_id)
        start_tokens, public_start = self._resolve_start_tokens(dataset, start_sequence, actual_seed)
        generated = self._generate_tokens(
            dataset=dataset,
            start_tokens=start_tokens,
            max_generate=max_generate,
            temperature=temperature,
            top_k=top_k,
            seed=actual_seed,
            sensor_tokens=sensor_tokens,
        )
        strategy = "sensor_profile" if sensor_tokens else "top_k"
        return {
            "client_id": client_id,
            "start_sequence": public_start,
            "generated_tokens": generated,
            "generated_times": [_time_delta_days(token) for token in generated],
            "model_version": MODEL_VERSION,
            "decoder_config": {
                "strategy": strategy,
                "top_k": top_k,
                "temperature": temperature,
                "max_generate": max_generate,
                "seed": actual_seed,
            },
        }

    def run_beam(
        self,
        client_id: str,
        start_sequence: list[str] | None,
        beam_width: int = 4,
        horizon: int = 16,
        temperature: float = 1.0,
        sensor_tokens: list[str] | None = None,
    ) -> list[dict[str, object]]:
        """Return ranked beam trajectories by joint log probability.

        Example:
            `run_beam("nexus_lab_solutions", [], beam_width=2, horizon=3)` returns
            two ranked dictionaries with `tokens` and `time_deltas`.
        """
        if beam_width < 1 or beam_width > 8:
            raise ValueError("beam_width must be between 1 and 8.")
        if horizon < 1 or horizon > 80:
            raise ValueError("horizon must be between 1 and 80.")
        if not 0.1 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0.1 and 2.0.")

        dataset = self._dataset_for(client_id)
        start_tokens, _public_start = self._resolve_start_tokens(dataset, start_sequence, seed=42)
        state = self._prepare_decoder(dataset, seed=42, sensor_tokens=sensor_tokens)
        beams: list[tuple[list[str], list[str], set[int], float]] = [(start_tokens, [], set(), 0.0)]

        for step in range(horizon):
            expanded: list[tuple[list[str], list[str], set[int], float]] = []
            for context_tokens, generated_tokens, used_indices, score in beams:
                if step == 0:
                    candidates = [
                        (token, None, token_score)
                        for token, token_score in self._time_candidates(state, context_tokens, beam_width)
                    ]
                else:
                    candidates = self._product_candidates(
                        state,
                        context_tokens,
                        used_indices,
                        temperature,
                        beam_width,
                    )

                for token, global_index, token_score in candidates:
                    next_used = set(used_indices)
                    if global_index is not None:
                        next_used.add(global_index)
                    expanded.append(
                        (
                            [*context_tokens, token],
                            [*generated_tokens, token],
                            next_used,
                            score + token_score,
                        )
                    )

            beams = sorted(expanded, key=lambda item: item[3], reverse=True)[:beam_width]

        return [
            {
                "rank": rank,
                "joint_log_prob": round(score, 6),
                "tokens": generated_tokens,
                "time_deltas": [_time_delta_days(token) for token in generated_tokens],
            }
            for rank, (_context_tokens, generated_tokens, _used_indices, score) in enumerate(beams, start=1)
        ]

    def list_clients(self) -> list[str]:
        """Return client ids from the protected dataset bundle.

        Example:
            `list_clients()` includes `"nexus_lab_solutions"` when the bundle is mounted.
        """
        return sorted(self._datasets().keys())

    def vocab_for_client(self, client_id: str) -> list[str]:
        """Return the runtime vocabulary for token matching without committing it.

        Example:
            `len(vocab_for_client("nexus_lab_solutions")) > 0` is true for a mounted bundle.
        """
        dataset = self._dataset_for(client_id)
        return list(getattr(dataset, "vocab", []))

    def _sensor_distribution_probe(
        self,
        client_id: str,
        start_sequence: list[str] | None,
        sensor_tokens: list[str],
        top_k: int = 8,
        temperature: float = 1.0,
        seed: int | None = None,
    ) -> list[dict[str, object]]:
        """Return top next-product probabilities for sensor Q&A tests.

        Example:
            `_sensor_distribution_probe("nexus_lab_solutions", [], ["token"], top_k=3)`
            returns top product tokens with probabilities after the first time token.
        """
        actual_seed = _coerce_seed(seed)
        self._validate_generation_args(max_generate=1, top_k=top_k, temperature=temperature)
        dataset = self._dataset_for(client_id)
        start_tokens, _public_start = self._resolve_start_tokens(dataset, start_sequence, actual_seed)
        state = self._prepare_decoder(dataset, actual_seed, sensor_tokens)
        time_token, _time_score = self._time_candidates(state, start_tokens, limit=1)[0]
        candidates = self._product_candidates(
            state,
            [*start_tokens, time_token],
            used_global_indices=set(),
            temperature=temperature,
            limit=top_k,
        )
        return [
            {
                "token": token,
                "probability": exp(score),
                "log_prob": round(score, 6),
            }
            for token, _global_index, score in candidates
        ]

    def _datasets(self) -> dict[str, Any]:
        """Load protected datasets lazily through `SimulationDataset`."""
        if self._dataset_map is not None:
            return self._dataset_map

        self._assert_artifacts_exist()
        import sys

        import joblib

        import_dir = self._prepared_import_dir()
        artifact_path = str(import_dir)
        if artifact_path not in sys.path:
            sys.path.insert(0, artifact_path)

        from alit_backend import SimulationDataset

        data_list = joblib.load(self.dataset_path)
        datasets = [SimulationDataset(preloaded_data=item) for item in data_list]
        self._dataset_map = {str(dataset.client_name): dataset for dataset in datasets}
        return self._dataset_map

    def _dataset_for(self, client_id: str) -> Any:
        """Return one protected dataset or raise with available ids."""
        datasets = self._datasets()
        if client_id not in datasets:
            available_clients = ", ".join(sorted(datasets))
            raise ValueError(f"Unknown client_id={client_id}. Available clients: {available_clients}.")
        return datasets[client_id]

    def _session_for(self) -> Any:
        """Load the ONNX runtime session once per process."""
        if self._session is None:
            self._assert_artifacts_exist()
            import onnxruntime as ort

            self._session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        return self._session

    def _assert_artifacts_exist(self) -> None:
        """Validate the protected artifact directory before importing protected code."""
        missing = [
            str(path)
            for path in (self.model_path, self.dataset_path, self.artifact_dir / "alit_backend.py")
            if not path.exists()
        ]
        if missing:
            raise ValueError(
                "Real model artifacts are not configured. Mount the NDA bundle and set "
                "REAL_MODEL_ARTIFACT_DIR. "
                f"Missing: {', '.join(missing)}"
            )

    def _prepared_import_dir(self) -> Path:
        """Return a runtime import directory with the platform runtime staged."""
        if self._import_dir is not None:
            return self._import_dir

        runtime_source = self._runtime_source()
        if runtime_source is None:
            self._import_dir = self.artifact_dir
            return self._import_dir

        runtime_dir = Path(environ.get("REAL_MODEL_RUNTIME_CACHE", "/tmp/swiftforecast_real_model_runtime"))
        package_dir = runtime_dir / "pyarmor_runtime_000000"
        package_dir.mkdir(parents=True, exist_ok=True)

        copy2(self.artifact_dir / "alit_backend.py", runtime_dir / "alit_backend.py")
        copy2(self.artifact_dir / "pyarmor_runtime_000000" / "__init__.py", package_dir / "__init__.py")
        copy2(runtime_source, package_dir / "pyarmor_runtime.so")

        self._import_dir = runtime_dir
        return self._import_dir

    def _runtime_source(self) -> Path | None:
        """Select the bundled PyArmor runtime for the current platform."""
        runtime_root = self.artifact_dir / "pyarmor_runtime_000000"
        if platform.startswith("linux"):
            candidate = runtime_root / "linux_x86_64" / "pyarmor_runtime.so"
        elif platform == "darwin":
            candidate = runtime_root / "darwin_universal" / "pyarmor_runtime.so"
        elif platform.startswith("win"):
            candidate = runtime_root / "windows_x86_64" / "pyarmor_runtime.pyd"
        else:
            candidate = runtime_root / "pyarmor_runtime.so"
        return candidate if candidate.exists() else None

    def _validate_generation_args(self, max_generate: int, top_k: int, temperature: float) -> None:
        """Validate shared decoder controls."""
        if max_generate < 1 or max_generate > 80:
            raise ValueError("max_generate must be between 1 and 80.")
        if top_k < 1 or top_k > 100:
            raise ValueError("top_k must be between 1 and 100.")
        if not 0.1 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0.1 and 2.0.")

    def _resolve_start_tokens(
        self,
        dataset: Any,
        start_sequence: list[str] | None,
        seed: int,
    ) -> tuple[list[str], list[str]]:
        """Resolve model context and public start sequence."""
        if start_sequence:
            return list(start_sequence), list(start_sequence)

        sentences = list(getattr(dataset, "sentences", []))
        if not sentences:
            raise ValueError("No sample sentences available for this client.")
        return Random(seed).choice(sentences).split(), []

    def _prepare_decoder(
        self,
        dataset: Any,
        seed: int,
        sensor_tokens: list[str] | None,
    ) -> _DecoderState:
        """Prepare arrays needed for decoder scoring."""
        import numpy as np

        rng = np.random.RandomState(seed)
        session = self._session_for()
        word_to_int = dataset.word_to_int
        vocab = dataset.vocab
        raw_vectors = dataset.all_vectors
        time_tokens = dataset.master_w2v.time_order
        vector_size = raw_vectors.shape[1]

        valid_indices = [index for index, word in enumerate(vocab) if word in word_to_int]
        selected_sensor_indices = self._sensor_indices(valid_indices, word_to_int, sensor_tokens, rng)
        sensor_input = np.zeros((1, self.vector_size, vector_size), dtype=np.float32)
        for sensor_offset, vocab_index in enumerate(selected_sensor_indices):
            sensor_input[0, sensor_offset] = raw_vectors[vocab_index]

        product_mask = np.array(
            [not (str(word).startswith("<dt_") or word == "<unk>") or word == "<eos>" for word in vocab]
        )
        product_indices = np.where(product_mask)[0]
        raw_candidates = raw_vectors[product_indices]
        dummy_sequence = np.zeros((1, self.current_seq_len, vector_size), dtype=np.float32)
        dummy_catalog = np.zeros((1, self.max_catalog_size, vector_size), dtype=np.float32)
        outputs = session.run(
            None,
            {
                "sentence_input": dummy_sequence,
                "catalog_input": dummy_catalog,
                "sensor_input": sensor_input,
            },
        )
        transform = outputs[3][0]
        aligned_candidates = np.dot(raw_candidates, transform)

        return _DecoderState(
            dataset=dataset,
            session=session,
            word_to_int=word_to_int,
            vocab=vocab,
            raw_vectors=raw_vectors,
            time_tokens=time_tokens,
            product_indices=product_indices,
            aligned_candidates=aligned_candidates,
            sensor_input=sensor_input,
            dummy_catalog=dummy_catalog,
            vector_size=vector_size,
        )

    def _sensor_indices(
        self,
        valid_indices: list[int],
        word_to_int: dict[str, int],
        sensor_tokens: list[str] | None,
        rng: Any,
    ) -> list[int]:
        """Build sensor indices, seeding them with personalization tokens when present."""
        import numpy as np

        selected = [word_to_int[token] for token in sensor_tokens or [] if token in word_to_int]
        remaining_count = max(0, self.vector_size - len(selected))
        replace_flag = len(valid_indices) < max(remaining_count, 1)
        random_indices = list(rng.choice(valid_indices, size=remaining_count, replace=replace_flag))
        return [*selected[: self.vector_size], *random_indices][: self.vector_size]

    def _generate_tokens(
        self,
        dataset: Any,
        start_tokens: list[str],
        max_generate: int,
        temperature: float,
        top_k: int,
        seed: int,
        sensor_tokens: list[str] | None,
    ) -> list[str]:
        """Generate tokens using top-k sampling with product uniqueness."""
        import numpy as np

        rng = np.random.RandomState(seed)
        state = self._prepare_decoder(dataset, seed, sensor_tokens)
        tokens = list(start_tokens)
        generated: list[str] = []
        used_product_indices: set[int] = set()

        for step in range(max_generate):
            if step == 0:
                time_token, _score = self._time_candidates(state, tokens, limit=1)[0]
                tokens.append(time_token)
                generated.append(time_token)
                continue

            candidates = self._product_candidates(state, tokens, used_product_indices, temperature, top_k)
            probabilities = np.array([candidate[2] for candidate in candidates], dtype=np.float64)
            probabilities = np.exp(probabilities - np.max(probabilities))
            probabilities = probabilities / np.sum(probabilities)
            selected_index = int(rng.choice(np.arange(len(candidates)), p=probabilities))
            next_word, global_index, _score = candidates[selected_index]
            if next_word == "<eos>":
                break
            tokens.append(next_word)
            generated.append(next_word)
            if global_index is not None:
                used_product_indices.add(global_index)

        if generated and str(generated[-1]).startswith("<dt_"):
            generated.pop()
        return generated

    def _model_outputs(self, state: _DecoderState, tokens: list[str]) -> tuple[Any, Any]:
        """Run ONNX inference for the current sequence context."""
        import numpy as np

        sentence_input = np.zeros((1, self.current_seq_len, state.vector_size), dtype=np.float32)
        recent = tokens[-self.current_seq_len :]
        for token_offset, token in enumerate(recent):
            if token in state.word_to_int:
                sentence_input[0, token_offset] = state.raw_vectors[state.word_to_int[token]]
        outputs = state.session.run(
            None,
            {
                "sentence_input": sentence_input,
                "catalog_input": state.dummy_catalog,
                "sensor_input": state.sensor_input,
            },
        )
        last_idx = max(0, len(recent) - 1)
        return outputs[1][0, last_idx, :], outputs[2][0, last_idx, :]

    def _time_candidates(self, state: _DecoderState, tokens: list[str], limit: int) -> list[tuple[str, float]]:
        """Return top time-token candidates and log probabilities."""
        import numpy as np

        time_scores, _query = self._model_outputs(state, tokens)
        probabilities = np.asarray(time_scores, dtype=np.float64)
        probabilities = np.maximum(probabilities, 0.0)
        if probabilities.sum() <= 0:
            probabilities = np.ones_like(probabilities, dtype=np.float64)
        probabilities = probabilities / probabilities.sum()
        search_slice = probabilities[1:] if len(probabilities) > 1 else probabilities
        offset = 1 if len(probabilities) > 1 else 0
        local_indices = np.argsort(search_slice)[-limit:][::-1]
        candidates: list[tuple[str, float]] = []
        for local_index in local_indices:
            time_index = int(local_index) + offset
            if time_index < len(state.time_tokens):
                candidates.append((str(state.time_tokens[time_index]), log(max(float(probabilities[time_index]), 1e-12))))
        if not candidates and state.time_tokens:
            candidates.append((str(state.time_tokens[0]), log(1e-12)))
        return candidates

    def _product_candidates(
        self,
        state: _DecoderState,
        tokens: list[str],
        used_global_indices: set[int],
        temperature: float,
        limit: int,
    ) -> list[tuple[str, int | None, float]]:
        """Return top product candidates and log probabilities."""
        import numpy as np

        _time_scores, query = self._model_outputs(state, tokens)
        product_logits = np.dot(state.aligned_candidates, query)
        for global_index in used_global_indices:
            local_locations = np.where(state.product_indices == global_index)[0]
            if len(local_locations) > 0:
                product_logits[local_locations[0]] = -1e10
        product_logits = product_logits / max(temperature, 1e-6)
        probabilities = _softmax(product_logits)
        candidate_count = min(limit, len(probabilities))
        local_indices = np.argsort(probabilities)[-candidate_count:][::-1]
        return [
            (
                str(state.vocab[int(state.product_indices[local_index])]),
                int(state.product_indices[local_index]),
                log(max(float(probabilities[local_index]), 1e-12)),
            )
            for local_index in local_indices
        ]


def get_default_model() -> RealSequenceModel:
    """Return a cached model using `REAL_MODEL_ARTIFACT_DIR`.

    Example:
        `get_default_model().list_clients()` reads the mounted artifact bundle.
    """
    global _DEFAULT_MODEL
    artifact_dir = getenv("REAL_MODEL_ARTIFACT_DIR")
    if not artifact_dir:
        raise ValueError("REAL_MODEL_ARTIFACT_DIR is not set.")
    if _DEFAULT_MODEL is None or str(_DEFAULT_MODEL.artifact_dir) != str(Path(artifact_dir).expanduser().resolve()):
        _DEFAULT_MODEL = RealSequenceModel(artifact_dir)
    return _DEFAULT_MODEL


def predict_basket(
    client_id: str,
    start_sequence: list[str] | None,
    max_generate: int = 32,
    top_k: int = 5,
    temperature: float = 1.0,
    seed: int | None = None,
) -> dict[str, object]:
    """Module-level handoff for Lane A's `predict_next_basket` tool.

    Example:
        `predict_basket("nexus_lab_solutions", [], max_generate=2)` returns the tool payload.
    """
    return get_default_model().predict_basket(
        client_id=client_id,
        start_sequence=start_sequence,
        max_generate=max_generate,
        top_k=top_k,
        temperature=temperature,
        seed=seed,
    )


def _split_sequence(start_sequence: str | None) -> list[str] | None:
    """Split a legacy string start sequence into tokens."""
    if start_sequence is None:
        return None
    return start_sequence.split()


def _coerce_seed(seed: int | None) -> int:
    """Normalize optional seeds for deterministic demo calls."""
    return 42 if seed is None else int(seed)


def _time_delta_days(token: str) -> int:
    """Convert a model time token into a dashboard-friendly day delta."""
    cleaned = token.strip("<>").lower()
    if not cleaned.startswith("dt_"):
        return 0
    suffix = cleaned.removeprefix("dt_")
    digits = "".join(character for character in suffix if character.isdigit())
    if not digits:
        return 0
    value = int(digits)
    if suffix.endswith("w"):
        return value * 7
    if suffix.endswith("m"):
        return value * 30
    if suffix.endswith("y"):
        return value * 365
    return value


def _softmax(values: Any) -> Any:
    """Return a stable softmax for numpy arrays."""
    import numpy as np

    shifted = values - np.max(values)
    exponentials = np.exp(shifted)
    total = np.sum(exponentials)
    if total <= 0:
        return np.ones_like(values, dtype=np.float64) / len(values)
    return exponentials / total
