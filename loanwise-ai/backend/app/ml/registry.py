"""
Model registry: loads the active model artifact with content-hash
verification (Section 8.3 — "a tampered .pkl file can't silently
substitute a different model").

In this reference implementation the registry is backed by the
`model_versions` table (source of truth for `is_active`) plus the
artifact + manifest files on disk. A real deployment would put artifacts
in object storage (S3/GCS) with the same hash-verification contract.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading

import joblib
import pandas as pd

from ml.explain import ExplanationService
from ml.preprocessing import ALL_FEATURES, get_feature_names

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "artifacts")


class ArtifactIntegrityError(Exception):
    pass


class ModelRegistry:
    """Thread-safe holder for the currently-active model + explainer.

    Call `.load(manifest)` once at startup and whenever an admin activates
    a new model version; reads are lock-free after that (swap a reference,
    don't mutate in place).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._active = None  # dict: model, explainer, manifest

    def load_from_manifest(self, manifest: dict, background_df: pd.DataFrame) -> None:
        artifact_path = manifest["artifact_path"]
        expected_hash = manifest["content_hash"]

        with open(artifact_path, "rb") as f:
            content = f.read()
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            raise ArtifactIntegrityError(
                f"Content hash mismatch for {artifact_path}: "
                f"expected {expected_hash}, got {actual_hash}. Refusing to load."
            )

        model = joblib.load(artifact_path)
        pipeline = model
        if hasattr(model, "calibrated_classifiers_"):
            inner = model.calibrated_classifiers_[0].estimator
            pipeline = inner.estimator if hasattr(inner, "estimator") else inner
        prep = pipeline.named_steps["prep"]
        feature_names = get_feature_names(prep)

        explainer = ExplanationService(model, background_df[ALL_FEATURES], feature_names)

        with self._lock:
            self._active = {
                "model": model,
                "explainer": explainer,
                "manifest": manifest,
            }

    def load_latest(self) -> None:
        with open(os.path.join(ARTIFACT_DIR, "latest_manifest.json")) as f:
            manifest = json.load(f)
        background_df = pd.read_csv(os.path.join(ARTIFACT_DIR, "test_holdout.csv")).sample(
            n=min(200, 500), random_state=1
        )
        self.load_from_manifest(manifest, background_df)

    @property
    def active(self) -> dict:
        if self._active is None:
            raise RuntimeError("No active model loaded. Call load_latest() at startup.")
        return self._active


registry = ModelRegistry()
