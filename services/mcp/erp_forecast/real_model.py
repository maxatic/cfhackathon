from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any


@dataclass(frozen=True)
class RealSequencePrediction:
    client_id: str
    start_sequence: str
    generated_sequence: str
    max_generate: int
    temperature: float
    top_k: int
    seed: int

    def to_dict(self) -> dict[str, object]:
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


class RealSequenceModel:
    """Thin adapter around the NDA-provided ONNX model and protected dataset class.

    This module deliberately treats alit_backend as a black box. It only imports the
    public SimulationDataset class and follows the inference contract from the CTO
    notebook.
    """

    def __init__(
        self,
        artifact_dir: str,
        model_filename: str = "landing_page_model.onnx",
        dataset_filename: str = "multi_client_dataset.joblib",
    ) -> None:
        self.artifact_dir = Path(artifact_dir).expanduser().resolve()
        self.model_path = self.artifact_dir / model_filename
        self.dataset_path = self.artifact_dir / dataset_filename
        self.vector_size = 128
        self.max_catalog_size = 256
        self.max_seq_len = 512
        self.current_seq_len = self.max_seq_len - 1
        self._session: Any | None = None
        self._dataset_map: dict[str, Any] | None = None

    def predict(
        self,
        client_id: str,
        start_sequence: str | None = None,
        max_generate: int = 30,
        temperature: float = 1.0,
        top_k: int = 30,
        seed: int = 42,
    ) -> RealSequencePrediction:
        if max_generate < 1 or max_generate > 80:
            raise ValueError("max_generate must be between 1 and 80.")
        if top_k < 1 or top_k > 100:
            raise ValueError("top_k must be between 1 and 100.")
        if not 0.1 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0.1 and 2.0.")

        dataset = self._dataset_for(client_id)
        if start_sequence is None:
            sentences = list(getattr(dataset, "sentences", []))
            if not sentences:
                raise ValueError(f"No sample sentences available for client_id={client_id}.")
            start_sequence = Random(seed).choice(sentences)

        generated = self._smart_inference_onnx(
            dataset=dataset,
            start_text=start_sequence,
            max_generate=max_generate,
            temperature=temperature,
            top_k=top_k,
            seed=seed,
        )
        return RealSequencePrediction(
            client_id=client_id,
            start_sequence=start_sequence,
            generated_sequence=generated,
            max_generate=max_generate,
            temperature=temperature,
            top_k=top_k,
            seed=seed,
        )

    def list_clients(self) -> list[str]:
        return sorted(self._datasets().keys())

    def _datasets(self) -> dict[str, Any]:
        if self._dataset_map is not None:
            return self._dataset_map

        self._assert_artifacts_exist()
        import sys

        import joblib

        artifact_path = str(self.artifact_dir)
        if artifact_path not in sys.path:
            sys.path.insert(0, artifact_path)

        from alit_backend import SimulationDataset

        data_list = joblib.load(self.dataset_path)
        datasets = [SimulationDataset(preloaded_data=item) for item in data_list]
        self._dataset_map = {str(dataset.client_name): dataset for dataset in datasets}
        return self._dataset_map

    def _dataset_for(self, client_id: str) -> Any:
        datasets = self._datasets()
        if client_id not in datasets:
            available_clients = ", ".join(sorted(datasets))
            raise ValueError(f"Unknown client_id={client_id}. Available clients: {available_clients}.")
        return datasets[client_id]

    def _session_for(self) -> Any:
        if self._session is None:
            self._assert_artifacts_exist()
            import onnxruntime as ort

            self._session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        return self._session

    def _assert_artifacts_exist(self) -> None:
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

    def _smart_inference_onnx(
        self,
        dataset: Any,
        start_text: str,
        max_generate: int,
        temperature: float,
        top_k: int,
        seed: int,
    ) -> str:
        import numpy as np

        rng = np.random.RandomState(seed)
        session = self._session_for()
        word_to_int = dataset.word_to_int
        vocab = dataset.vocab
        raw_vectors = dataset.all_vectors
        time_tokens = dataset.master_w2v.time_order
        vector_size = raw_vectors.shape[1]

        valid_indices = [i for i, word in enumerate(vocab) if word in word_to_int]
        replace_flag = len(valid_indices) < self.vector_size
        sensor_indices = rng.choice(valid_indices, size=self.vector_size, replace=replace_flag)

        sensor_input = np.zeros((1, self.vector_size, vector_size), dtype=np.float32)
        for sensor_offset, vocab_index in enumerate(sensor_indices):
            sensor_input[0, sensor_offset] = raw_vectors[vocab_index]

        product_mask = np.array(
            [
                not (word.startswith("<dt_") or word == "<unk>") or word == "<eos>"
                for word in vocab
            ]
        )
        product_indices = np.where(product_mask)[0]
        raw_candidates = raw_vectors[product_indices]

        dummy_seq = np.zeros((1, self.current_seq_len, vector_size), dtype=np.float32)
        dummy_cat = np.zeros((1, self.max_catalog_size, vector_size), dtype=np.float32)

        outputs = session.run(
            None,
            {
                "sentence_input": dummy_seq,
                "catalog_input": dummy_cat,
                "sensor_input": sensor_input,
            },
        )
        transform = outputs[3][0]
        aligned_candidates = np.dot(raw_candidates, transform)

        tokens = start_text.split()
        generated: list[str] = []
        generated_product_indices: set[int] = set()

        for step in range(max_generate):
            sentence_input = np.zeros((1, self.current_seq_len, vector_size), dtype=np.float32)
            recent = tokens[-self.current_seq_len :]
            for token_offset, token in enumerate(recent):
                if token in word_to_int:
                    sentence_input[0, token_offset] = raw_vectors[word_to_int[token]]

            loop_outputs = session.run(
                None,
                {
                    "sentence_input": sentence_input,
                    "catalog_input": dummy_cat,
                    "sensor_input": sensor_input,
                },
            )
            time_probs_seq = loop_outputs[1]
            query_seq = loop_outputs[2]
            last_idx = len(recent) - 1
            time_probs = time_probs_seq[0, last_idx, :]

            if step == 0:
                first_time_token = time_tokens[int(np.argmax(time_probs[1:]))]
                tokens.append(first_time_token)
                generated.append(first_time_token)
                continue

            product_logits = np.dot(aligned_candidates, query_seq[0, last_idx, :])
            for global_index in generated_product_indices:
                local_locs = np.where(product_indices == global_index)[0]
                if len(local_locs) > 0:
                    product_logits[local_locs[0]] = -1e10

            product_logits /= max(temperature, 1e-6)
            exp_logits = np.exp(product_logits - np.max(product_logits))
            probabilities = exp_logits / np.sum(exp_logits)
            top_k_idx = np.argsort(probabilities)[-top_k:]
            top_probs = probabilities[top_k_idx] / np.sum(probabilities[top_k_idx])
            selected_local_idx = rng.choice(top_k_idx, p=top_probs)

            global_idx = product_indices[selected_local_idx]
            next_word = vocab[global_idx]
            if next_word == "<eos>":
                generated.append(time_tokens[int(np.argmax(time_probs[1:]))])
                break

            tokens.append(next_word)
            generated.append(next_word)
            generated_product_indices.add(global_idx)

        if generated and generated[-1].startswith("<dt_"):
            generated.pop()
        return " ".join(generated)
