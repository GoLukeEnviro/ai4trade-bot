#!/usr/bin/env python3
"""XGBoost model training script for the ai4trade-bot PredictiveEngine.

Usage:
    python scripts/train_xgboost.py --data path/to/ohlcv.csv --output models/predictive/
    python scripts/train_xgboost.py --data path/to/ohlcv.csv --output models/predictive/ --test-size 0.2

The input CSV must contain columns: open, high, low, close, volume
Optionally: timestamp (datetime), or the DataFrame index will be used.

The script:
1. Validates input schema
2. Builds features via core.feature_pipeline.FeaturePipeline
3. Creates binary labels (price up/down next period)
4. Trains an XGBoost classifier
5. Saves the model to models/predictive/xgboost_v1.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("train_xgboost")


REQUIRED_COLUMNS = {"open", "high", "low", "close"}


def validate_schema(df: pd.DataFrame) -> None:
    """Validate that the DataFrame has the required OHLCV columns."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Input data missing required columns: {missing}. "
            f"Required: {REQUIRED_COLUMNS}, got: {list(df.columns)}"
        )
    if len(df) < 30:
        raise ValueError(
            f"Input data too small: {len(df)} rows. Minimum 30 rows required."
        )


def load_data(path: str) -> pd.DataFrame:
    """Load OHLCV data from CSV or Parquet file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    if p.suffix == ".parquet":
        df = pd.read_parquet(path)
    elif p.suffix in (".csv", ".feather"):
        if p.suffix == ".feather":
            df = pd.read_feather(path)
        else:
            df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported file format: {p.suffix}. Use .csv, .feather, or .parquet")

    if "timestamp" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")

    log.info("Loaded %d rows from %s", len(df), path)
    return df


def build_features_and_labels(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Build features and binary labels from OHLCV data."""
    from core.feature_pipeline import FeaturePipeline

    pipeline = FeaturePipeline()
    features = pipeline.build_features(df)

    # Drop rows with all NaN features
    features = features.dropna(how="all")
    if len(features) < 10:
        raise ValueError(
            f"Not enough non-NaN feature rows: {len(features)}. Need at least 10."
        )

    # Binary label: 1 if close goes up next period, 0 otherwise
    close = features["close"]
    future_close = close.shift(-1)
    labels = (future_close > close).astype(int).values

    # Drop last row (no label) and first rows with NaN features
    valid_mask = ~np.isnan(labels) & features.notna().all(axis=1)
    features = features[valid_mask]
    labels = labels[valid_mask]

    log.info("Features: %d rows, %d columns", len(features), len(features.columns))
    log.info("Labels: %d UP, %d DOWN", labels.sum(), len(labels) - labels.sum())

    return features, labels


def train_model(
    features: pd.DataFrame,
    labels: np.ndarray,
    test_size: float = 0.2,
) -> object:
    """Train XGBoost classifier and return the trained booster."""
    from xgboost import XGBClassifier

    # Drop non-feature columns
    feature_cols = [
        c
        for c in features.columns
        if c not in ("fear_greed_class",)
        and features[c].dtype in (np.float64, np.float32, np.int64, np.int32, float, int)
        and features[c].notna().all()
    ]

    X = features[feature_cols].fillna(0).values
    y = labels

    split_idx = int(len(X) * (1 - test_size))
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    model = XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        objective="binary:logistic",
        eval_metric="logloss",
        use_label_encoder=False,
        random_state=42,
    )
    model.fit(X_train, y_train)

    train_acc = model.score(X_train, y_train)
    test_acc = model.score(X_test, y_test)
    log.info("Train accuracy: %.4f", train_acc)
    log.info("Test accuracy:  %.4f", test_acc)

    return model


def save_model(model, output_dir: str) -> Path:
    """Save the trained model to the specified directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    model_path = out / "xgboost_v1.json"
    model.get_booster().save_model(str(model_path))
    log.info("Model saved to %s", model_path)

    # Save feature column names for inference
    meta_path = out / "xgboost_v1_meta.txt"
    # We'll just write a note; the inference code in predictive.py
    # handles column selection dynamically
    meta_path.write_text("Model: xgboost_v1\nTrained by: scripts/train_xgboost.py\n")
    log.info("Metadata saved to %s", meta_path)

    return model_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train XGBoost model for ai4trade-bot PredictiveEngine"
    )
    parser.add_argument(
        "--data", required=True, help="Path to OHLCV CSV/feather/parquet file"
    )
    parser.add_argument(
        "--output",
        default="models/predictive/",
        help="Output directory for trained model (default: models/predictive/)",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Fraction of data for test split (default: 0.2)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    log.info("=== XGBoost Training Pipeline ===")
    log.info("Data: %s", args.data)
    log.info("Output: %s", args.output)

    try:
        df = load_data(args.data)
        validate_schema(df)

        features, labels = build_features_and_labels(df)

        model = train_model(features, labels, test_size=args.test_size)

        model_path = save_model(model, args.output)

        log.info("=== Training complete ===")
        log.info("Model: %s", model_path)
        sys.exit(0)
    except Exception as exc:
        log.error("Training failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
