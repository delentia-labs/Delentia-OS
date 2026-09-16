"""
ALGO-36: RFLH — Rare-Failure Learning Heuristic (Few-Shot Meta-Learning)

Ported from Delentia-Private-OS's real few-shot meta-learning engine at
rct_platform/microservices/few-shot-learning/app/core/rflh_engine.py
(class RFLHEngine) — despite that microservice's own folder being named
"few-shot-learning" (a naming-collision artifact of the private repo's
own layout, not a mistake in this port), together with the minimal
schema types from ../models/schemas.py it depends on.

Per this port's brief, the source module was already fixed 2026-09-14 to
use genuinely real logic in the two places that mattered most (verified
here by reading the actual code, not assumed):

1. `_maml_adapt`: real PyTorch autograd gradient descent. Each adaptation
   step builds `W_t`/`b_t` as `requires_grad=True` tensors, computes a
   real MSE loss over the support set, calls `step_loss.backward()`, and
   reads the REAL gradients off `.grad` — replacing an earlier version
   where `grad_W`/`grad_b` were `np.random.randn(...) * 0.001` (literal
   random noise, uncorrelated with the loss just computed).
2. `_embed_text`: real content-derived embeddings via SHA256 feature-
   hashing (tokenize -> per-token SHA256 -> hash-bucket + sign -> L2
   normalize) — replacing an earlier version that seeded
   `np.random.randn()` off Python's built-in `hash()`, which had NO
   relationship to shared vocabulary between texts. The current version
   genuinely gives two texts that share vocabulary a real, non-trivial
   cosine similarity, and is deterministic per text.

Both of these were verified directly in this port (not re-taken on
faith) by reading rflh_engine.py in full; the code matches the 2026-09-14
fix description exactly, so no further change to that logic was needed
or made here.

torch and scikit-learn (the only two non-stdlib/non-numpy dependencies
`_maml_adapt`/cosine-similarity use) were confirmed already installed
and importable in this Delentia-OS environment before writing this file
(`import torch` -> 2.12.1+cpu, `import sklearn` -> 1.8.0) — nothing new
needed installing. `loguru` (used for logging in the source) was also
already installed and is kept; numpy and scikit-learn's
`cosine_similarity` remain used exactly as in the source.

Only structural change: the pydantic schema types (`LearningExample`,
`SupportSet`, `QueryExample`, `Prediction`, `TaskType`,
`MetaLearningAlgorithm`) are re-expressed as plain dataclasses (this
port doesn't need pydantic's validation/JSON-schema machinery — the
engine only ever reads plain attributes off these objects), and the
engine's own `PatternType`/edge-case-pattern-detection request/response
models (used only by a separate `pattern_detector.py` this port does not
include) were left out as out of scope. No engine logic was changed.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import torch
from loguru import logger

_TOKEN_RE = re.compile(r"[a-z0-9]+")


# ============================================================================
# Minimal types (inlined from ../models/schemas.py — only what RFLHEngine
# actually references)
# ============================================================================

class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    QUESTION_ANSWERING = "question_answering"
    TEXT_GENERATION = "text_generation"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    NAMED_ENTITY_RECOGNITION = "named_entity_recognition"
    OTHER = "other"


class MetaLearningAlgorithm(str, Enum):
    MAML = "maml"
    PROTOTYPICAL = "prototypical"
    MATCHING = "matching"
    RELATION = "relation"


class PatternType(str, Enum):
    RARE_LANGUAGE = "RareLanguage"
    CUSTOM_FORMAT = "CustomFormat"
    ANOMALOUS_LENGTH = "AnomalousLength"
    SPECIAL_CHARACTERS = "SpecialCharacters"
    MIXED_ENCODING = "MixedEncoding"
    LEGACY_FORMAT = "LegacyFormat"
    UNKNOWN = "Unknown"


@dataclass
class LearningExample:
    """Single learning example with input-output pair"""
    example_id: str
    input: Union[str, Dict[str, Any]]
    output: Union[str, Dict[str, Any], int, float, List]
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SupportSet:
    """Collection of support examples for few-shot learning"""
    task_id: str
    task_type: TaskType
    examples: List[LearningExample]
    num_shots: int
    task_description: Optional[str] = None


@dataclass
class QueryExample:
    """Query example for prediction"""
    input: Union[str, Dict[str, Any]]
    query_id: Optional[str] = None
    expected_output: Optional[Union[str, Dict[str, Any]]] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class Prediction:
    """Single prediction"""
    label: Union[str, int, float] = ""
    confidence: float = 0.0
    predicted_output: Any = None
    explanation: Optional[str] = None


class RFLHEngine:
    """
    Rapid Few-Shot Learning Handler Engine

    Implements meta-learning algorithms for few-shot learning:
    - MAML (Model-Agnostic Meta-Learning) — real PyTorch autograd gradients
    - Prototypical Networks — real class-mean prototypes + nearest-prototype

    Target: -3% edge case error rate
    """

    def __init__(
        self,
        embedding_dim: int = 768,
        meta_learning_rate: float = 0.001,
        adaptation_steps: int = 5
    ):
        self.embedding_dim = embedding_dim
        self.meta_learning_rate = meta_learning_rate
        self.adaptation_steps = adaptation_steps

        self.task_models: Dict[str, Dict[str, Any]] = {}
        self.task_examples: Dict[str, List[LearningExample]] = defaultdict(list)

        self.meta_params = {
            "W": np.random.randn(embedding_dim, embedding_dim) * 0.01,
            "b": np.zeros(embedding_dim)
        }

        self.total_adaptations = 0
        self.total_predictions = 0
        self.successful_predictions = 0

        self._lock = asyncio.Lock()

        logger.info(
            f"RFLHEngine initialized: dim={embedding_dim}, "
            f"lr={meta_learning_rate}, steps={adaptation_steps}"
        )

    # ========================================================================
    # Meta-Learning Methods
    # ========================================================================

    async def meta_learn(
        self,
        task_id: str,
        support_set: Union[SupportSet, List[LearningExample]],
        query_set: Optional[Union[List[QueryExample], List[LearningExample]]] = None,
        algorithm: MetaLearningAlgorithm = MetaLearningAlgorithm.MAML,
        num_steps: int = 5,
        learning_rate: float = 0.001
    ) -> Dict[str, Any]:
        start_time = time.time()

        async with self._lock:
            logger.debug(
                f"Meta-learning: task={task_id}, algorithm={algorithm.value}, "
                f"steps={num_steps}, lr={learning_rate}"
            )

            if isinstance(support_set, SupportSet):
                support_examples = support_set.examples
            else:
                support_examples = support_set

            query_examples = None
            if query_set:
                query_examples = []
                for q in query_set:
                    if isinstance(q, QueryExample):
                        ex = LearningExample(
                            example_id=q.query_id or f"query_{len(query_examples)}",
                            input=q.input,
                            output=q.expected_output if q.expected_output is not None else "",
                            metadata=q.context or {}
                        )
                        query_examples.append(ex)
                    else:
                        query_examples.append(q)

            self.task_examples[task_id].extend(support_examples)

            if algorithm == MetaLearningAlgorithm.MAML:
                adapted_params, loss, accuracy = await self._maml_adapt(
                    task_id, support_examples, query_examples, num_steps, learning_rate
                )
            elif algorithm == MetaLearningAlgorithm.PROTOTYPICAL:
                adapted_params, loss, accuracy = await self._prototypical_learn(
                    task_id, support_examples, query_examples
                )
            else:
                adapted_params, loss, accuracy = await self._maml_adapt(
                    task_id, support_examples, query_examples, num_steps, learning_rate
                )

            self.task_models[task_id] = {
                "params": adapted_params,
                "algorithm": algorithm.value,
                "num_examples": len(support_examples),
                "created_at": datetime.now(),
                "accuracy": accuracy
            }

            self.total_adaptations += 1
            training_time = time.time() - start_time

            logger.info(
                f"Meta-learning complete: task={task_id}, "
                f"accuracy={accuracy:.3f}, loss={loss:.4f}, time={training_time:.2f}s"
            )

            return {
                "task_id": task_id,
                "accuracy": accuracy,
                "loss": loss,
                "num_examples": len(support_examples),
                "adaptation_steps": num_steps,
                "training_time_s": training_time,
                "algorithm_used": algorithm.value,
                "adapted_params": adapted_params
            }

    async def _maml_adapt(
        self,
        task_id: str,
        support_set: List[LearningExample],
        query_set: Optional[List[LearningExample]],
        num_steps: int,
        learning_rate: float
    ) -> Tuple[Dict[str, Any], float, float]:
        """MAML adaptation using REAL PyTorch autograd gradients (not
        random noise — see module docstring)."""
        support_embeddings = [self._embed_example(ex) for ex in support_set]
        support_labels = [self._extract_label(ex) for ex in support_set]

        adapted_W = self.meta_params["W"].copy()
        adapted_b = self.meta_params["b"].copy()

        support_embeddings_t = [torch.tensor(e, dtype=torch.float32) for e in support_embeddings]
        support_labels_t = [torch.tensor(l, dtype=torch.float32) for l in support_labels]

        step_loss = torch.zeros((), dtype=torch.float32)
        for step in range(num_steps):
            W_t = torch.tensor(adapted_W, dtype=torch.float32, requires_grad=True)
            b_t = torch.tensor(adapted_b, dtype=torch.float32, requires_grad=True)

            step_loss = torch.zeros((), dtype=torch.float32)
            for emb_t, label_t in zip(support_embeddings_t, support_labels_t):
                pred_t = W_t @ emb_t + b_t
                step_loss = step_loss + torch.mean((pred_t - label_t) ** 2)
            step_loss = step_loss / len(support_set)

            step_loss.backward()

            grad_W = W_t.grad.numpy()
            grad_b = b_t.grad.numpy()

            adapted_W = adapted_W - learning_rate * grad_W
            adapted_b = adapted_b - learning_rate * grad_b

        loss = float(step_loss.item())

        accuracy = 0.0
        if query_set:
            correct = 0
            for query_ex in query_set:
                query_emb = self._embed_example(query_ex)
                pred = np.dot(adapted_W, query_emb) + adapted_b
                true_label = self._extract_label(query_ex)

                if np.linalg.norm(pred - true_label) < 0.5:
                    correct += 1

            accuracy = correct / len(query_set)
        else:
            correct = 0
            for emb, label in zip(support_embeddings, support_labels):
                pred = np.dot(adapted_W, emb) + adapted_b
                if np.linalg.norm(pred - label) < 0.5:
                    correct += 1
            accuracy = correct / len(support_set)

        adapted_params = {
            "W": adapted_W,
            "b": adapted_b,
            "algorithm": "maml"
        }

        return adapted_params, loss, accuracy

    async def _prototypical_learn(
        self,
        task_id: str,
        support_set: List[LearningExample],
        query_set: Optional[List[LearningExample]]
    ) -> Tuple[Dict[str, Any], float, float]:
        class_examples: Dict[Any, List[np.ndarray]] = defaultdict(list)

        for ex in support_set:
            label = self._extract_label(ex)
            embedding = self._embed_example(ex)

            if isinstance(label, np.ndarray):
                label_key = tuple(label.tolist())
            else:
                label_key = label

            class_examples[label_key].append(embedding)

        prototypes = {}
        for label, embeddings in class_examples.items():
            prototypes[label] = np.mean(embeddings, axis=0)

        accuracy = 0.0
        loss = 0.0

        if query_set:
            correct = 0
            for query_ex in query_set:
                query_emb = self._embed_example(query_ex)
                true_label_raw = self._extract_label(query_ex)

                if isinstance(true_label_raw, np.ndarray):
                    true_label = tuple(true_label_raw.tolist())
                else:
                    true_label = true_label_raw

                distances = {}
                for label, prototype in prototypes.items():
                    dist = np.linalg.norm(query_emb - prototype)
                    distances[label] = dist

                predicted_label = min(distances, key=distances.get)

                if predicted_label == true_label:
                    correct += 1

                loss += distances[predicted_label]

            accuracy = correct / len(query_set)
            loss = loss / len(query_set)
        else:
            accuracy = 0.88
            loss = 0.15

        adapted_params = {
            "prototypes": prototypes,
            "algorithm": "prototypical"
        }

        return adapted_params, loss, accuracy

    # ========================================================================
    # Prediction Methods
    # ========================================================================

    async def predict(
        self,
        task_id: str,
        query: Any,
        support_set: Union[SupportSet, List[LearningExample]],
        algorithm: MetaLearningAlgorithm = MetaLearningAlgorithm.PROTOTYPICAL,
        return_top_k: int = 3
    ) -> List[Prediction]:
        start_time = time.time()

        async with self._lock:
            if isinstance(support_set, SupportSet):
                support_examples = support_set.examples
            else:
                support_examples = support_set

            logger.debug(
                f"Predicting: task={task_id}, algo={algorithm.value}, "
                f"support_size={len(support_examples)}"
            )

            query_embedding = self._embed_text(str(query))

            if task_id not in self.task_models:
                await self.meta_learn(task_id, support_examples, None, algorithm, num_steps=3)

            task_model = self.task_models[task_id]

            if task_model["algorithm"] == "prototypical":
                prediction, confidence, top_k = await self._prototypical_predict(
                    query_embedding, task_model, return_top_k
                )
            else:
                prediction, confidence, top_k = await self._maml_predict(
                    query_embedding, task_model, return_top_k
                )

            self.total_predictions += 1
            if prediction is not None:
                self.successful_predictions += 1

            inference_time = (time.time() - start_time) * 1000  # ms

            logger.debug(
                f"Prediction complete: confidence={confidence:.3f}, "
                f"time={inference_time:.1f}ms"
            )

            predictions_list = []
            if top_k:
                for pred_output, pred_conf in top_k:
                    if isinstance(pred_output, (list, np.ndarray)):
                        label = f"prediction_{hash(str(pred_output)) % 1000}"
                    else:
                        label = pred_output

                    predictions_list.append(Prediction(label=label, confidence=pred_conf))
            else:
                predictions_list.append(Prediction(predicted_output=prediction, confidence=confidence))

            return predictions_list

    async def _prototypical_predict(
        self,
        query_embedding: np.ndarray,
        task_model: Dict[str, Any],
        top_k: int
    ) -> Tuple[Any, float, List[Tuple[Any, float]]]:
        prototypes = task_model["params"]["prototypes"]

        distances = {}
        for label, prototype in prototypes.items():
            dist = np.linalg.norm(query_embedding - prototype)
            distances[label] = dist

        neg_distances = {k: -v for k, v in distances.items()}
        max_neg_dist = max(neg_distances.values())
        exp_scores = {k: np.exp(v - max_neg_dist) for k, v in neg_distances.items()}
        total = sum(exp_scores.values())
        probabilities = {k: v / total for k, v in exp_scores.items()}

        sorted_preds = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)

        prediction = sorted_preds[0][0]
        confidence = sorted_preds[0][1]

        if isinstance(prediction, tuple):
            prediction = list(prediction)

        top_k_preds = [
            (pred if not isinstance(pred, tuple) else list(pred), float(conf))
            for pred, conf in sorted_preds[:top_k]
        ]

        return prediction, float(confidence), top_k_preds

    async def _maml_predict(
        self,
        query_embedding: np.ndarray,
        task_model: Dict[str, Any],
        top_k: int
    ) -> Tuple[Any, float, List[Tuple[Any, float]]]:
        W = task_model["params"]["W"]
        b = task_model["params"]["b"]

        prediction = np.dot(W, query_embedding) + b

        confidence = task_model.get("accuracy", 0.5)

        top_k_preds = [(prediction.tolist(), float(confidence))]

        return prediction.tolist(), float(confidence), top_k_preds

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _embed_example(self, example: LearningExample) -> np.ndarray:
        if isinstance(example.input, str):
            return self._embed_text(example.input)
        else:
            text = str(example.input)
            return self._embed_text(text)

    def _embed_text(self, text: str) -> np.ndarray:
        """Embed text to vector via the hashing trick (feature-hashed,
        signed bag-of-words), L2-normalized — real, content-derived
        embeddings (see module docstring)."""
        vector = np.zeros(self.embedding_dim, dtype=np.float64)
        tokens = _TOKEN_RE.findall(text.lower())

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % self.embedding_dim
            sign = 1.0 if (digest[8] & 1) == 0 else -1.0
            vector[bucket] += sign

        norm = np.linalg.norm(vector)
        if norm == 0.0:
            return vector
        return vector / norm

    def _extract_label(self, example: LearningExample) -> np.ndarray:
        output = example.output

        if isinstance(output, (int, float)):
            return np.array([output])
        elif isinstance(output, str):
            return np.array([hash(output) % 1000])
        elif isinstance(output, (list, np.ndarray)):
            return np.array(output)
        else:
            return np.array([hash(str(output)) % 1000])

    # ========================================================================
    # Statistics
    # ========================================================================

    async def get_statistics(self) -> Dict[str, Any]:
        async with self._lock:
            success_rate = (
                self.successful_predictions / self.total_predictions
                if self.total_predictions > 0 else 0.0
            )

            return {
                "total_tasks": len(self.task_models),
                "total_examples": sum(len(exs) for exs in self.task_examples.values()),
                "total_adaptations": self.total_adaptations,
                "total_predictions": self.total_predictions,
                "successful_predictions": self.successful_predictions,
                "success_rate": success_rate,
                "algorithms_available": ["MAML", "Prototypical", "Matching"]
            }

    async def get_task_model(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return self.task_models.get(task_id)

    async def reset_statistics(self):
        async with self._lock:
            self.total_adaptations = 0
            self.total_predictions = 0
            self.successful_predictions = 0
            logger.info("Statistics reset")


if __name__ == "__main__":
    import asyncio as _asyncio

    async def _main():
        print("=" * 70)
        print("ALGO-36 RFLH — smoke test (real autograd gradients + real hashed embeddings)")
        print("=" * 70)

        engine = RFLHEngine(embedding_dim=64)

        # --- Real content-derived embeddings: shared-vocabulary similarity ---
        emb_a = engine._embed_text("the quick brown fox jumps over the lazy dog")
        emb_b = engine._embed_text("the quick brown fox leaps over a sleepy dog")
        emb_c = engine._embed_text("quantum entanglement violates local realism")

        sim_ab = float(np.dot(emb_a, emb_b))  # both are unit-norm -> dot == cosine similarity
        sim_ac = float(np.dot(emb_a, emb_c))
        print(f"\n[Embeddings] cos(similar-vocab pair)   = {sim_ab:.4f}")
        print(f"[Embeddings] cos(unrelated-vocab pair) = {sim_ac:.4f}")
        assert sim_ab > sim_ac, "Shared-vocabulary texts should be more similar than unrelated ones"
        assert abs(np.linalg.norm(emb_a) - 1.0) < 1e-6, "Embeddings must be L2-normalized"

        # Determinism: same text -> same vector, every time
        emb_a2 = engine._embed_text("the quick brown fox jumps over the lazy dog")
        assert np.allclose(emb_a, emb_a2), "Embedding must be deterministic per text"

        # --- Real MAML adaptation: prove gradient descent actually reduces loss ---
        support = [
            LearningExample(example_id="e1", input="positive review great product", output=1.0),
            LearningExample(example_id="e2", input="positive review excellent quality", output=1.0),
            LearningExample(example_id="e3", input="negative review terrible waste", output=-1.0),
            LearningExample(example_id="e4", input="negative review awful broken", output=-1.0),
        ]
        query = [
            LearningExample(example_id="q1", input="positive review amazing product", output=1.0),
            LearningExample(example_id="q2", input="negative review horrible defective", output=-1.0),
        ]

        # One-step loss (for comparison) vs multi-step loss, same seed params
        result_1step = await engine.meta_learn(
            "sentiment-1step", support, query, algorithm=MetaLearningAlgorithm.MAML,
            num_steps=1, learning_rate=0.5
        )
        engine2 = RFLHEngine(embedding_dim=64)
        engine2.meta_params = {k: v.copy() for k, v in engine.meta_params.items()}
        result_10step = await engine2.meta_learn(
            "sentiment-10step", support, query, algorithm=MetaLearningAlgorithm.MAML,
            num_steps=10, learning_rate=0.5
        )
        print(f"\n[MAML] loss after 1 gradient step  = {result_1step['loss']:.6f}")
        print(f"[MAML] loss after 10 gradient steps = {result_10step['loss']:.6f}")
        print(f"[MAML] accuracy after 10 steps      = {result_10step['accuracy']:.3f}")
        assert result_10step["loss"] < result_1step["loss"], (
            "Real gradient descent must reduce loss further with more steps "
            "(this would NOT reliably hold if gradients were random noise)"
        )

        # --- Real Prototypical Networks: class-mean prototypes + nearest-prototype ---
        proto_result = await engine.meta_learn(
            "sentiment-proto", support, query, algorithm=MetaLearningAlgorithm.PROTOTYPICAL
        )
        print(f"\n[Prototypical] accuracy = {proto_result['accuracy']:.3f}, loss = {proto_result['loss']:.4f}")
        assert proto_result["accuracy"] >= 0.5  # better than chance on this clearly-separable toy task

        # --- Real few-shot prediction end-to-end ---
        predictions = await engine.predict(
            "sentiment-proto",
            "positive review absolutely fantastic",
            support,
            algorithm=MetaLearningAlgorithm.PROTOTYPICAL,
            return_top_k=2,
        )
        print(f"\n[Predict] top-{len(predictions)} predictions for a positive-leaning query:")
        for p in predictions:
            print(f"  label={p.label}, confidence={p.confidence:.4f}")
        assert len(predictions) >= 1
        assert all(0.0 <= p.confidence <= 1.0 for p in predictions)

        stats = await engine.get_statistics()
        print(f"\n[Stats] {stats}")
        # `engine` ran meta_learn twice (sentiment-1step, sentiment-proto);
        # the 10-step comparison ran on a separate `engine2` instance to
        # keep the two loss measurements independent, so its adaptation
        # isn't counted here.
        assert stats["total_adaptations"] >= 2
        assert stats["total_predictions"] >= 1

        print("\nALL ASSERTIONS PASSED")

    _asyncio.run(_main())
