"""
ml_model.py — Feature 6: Machine Learning Price Prediction

PHASE 2 UPGRADE
────────────────
The original Random Forest model is preserved and remains the default
fallback. This module now:

  1. Trains and compares 4 candidates:
       - Linear Regression
       - Random Forest        (original model, kept)
       - Gradient Boosting
       - XGBoost (only if the `xgboost` package is installed; the system
         degrades gracefully otherwise)

  2. Computes for every candidate:
       - MAE   (Mean Absolute Error)
       - RMSE  (Root Mean Squared Error)
       - R²    (coefficient of determination)
       - MAPE  (Mean Absolute Percentage Error)

  3. Automatically selects the best-performing model (lowest RMSE) and
     persists it to price_model.pkl, exactly as before — so every existing
     caller (predict_price, analyze_apartment, get_model_meta, the
     /api/model-info and /api/ml-dashboard routes) keeps working unchanged.

  4. Stores the full comparison table + chosen model name inside `meta`
     under the new "model_comparison" / "selected_model" keys, which the
     dashboard can render as a table/chart (Phase 2 + Phase 6).

Backward compatibility
───────────────────────
- `train_model()`, `get_model_meta()`, `predict_price()`, `analyze_apartment()`
  keep their original signatures and return shapes (with new optional keys
  added, nothing removed).
- The on-disk pickle bundle keeps the same {"model","encoders","meta"} shape.
"""
import os
import pickle
import logging

import pandas as pd
import numpy as np

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBRegressor
    _HAS_XGBOOST = True
except ImportError:  # pragma: no cover - environment dependent
    _HAS_XGBOOST = False

DATA_PATH  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "housing.csv")
MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "price_model.pkl")

# Module-level cache
_model_cache      = None
_encoders_cache   = None
_model_meta_cache = None

FEATURES = ["ville", "quartier", "surface", "chambres", "salles_bain", "etage",
            "ascenseur_enc", "parking_enc", "terrasse_enc"]


# ══════════════════════════════════════════════════════════════════
#  ENCODING HELPERS  (unchanged behaviour)
# ══════════════════════════════════════════════════════════════════
def _encode_df(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One-hot encode binaries; label-encode categoricals (ville/quartier)."""
    df = df.copy()
    for col in ["ascenseur", "parking", "terrasse"]:
        df[col + "_enc"] = (df[col].str.lower() == "yes").astype(int)

    encoders = {}
    for col in ["ville", "quartier"]:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))
        encoders[col] = le
    return df, encoders


def _apply_encoders(df: pd.DataFrame, encoders: dict) -> pd.DataFrame:
    """Apply existing encoders (for prediction, not training)."""
    df = df.copy()
    for col in ["ascenseur", "parking", "terrasse"]:
        df[col + "_enc"] = (df[col].str.lower() == "yes").astype(int)
    for col in ["ville", "quartier"]:
        le = encoders[col]
        df[col] = df[col].astype(str).apply(
            lambda x: le.transform([x])[0] if x in le.classes_ else 0
        )
    return df


# ══════════════════════════════════════════════════════════════════
#  METRICS
# ══════════════════════════════════════════════════════════════════
def _compute_metrics(y_true, y_pred) -> dict:
    mae  = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2   = r2_score(y_true, y_pred)
    # Avoid division by zero in MAPE
    y_true_arr = np.asarray(y_true, dtype=float)
    nonzero = y_true_arr != 0
    if nonzero.any():
        mape = float(np.mean(np.abs((y_true_arr[nonzero] - np.asarray(y_pred)[nonzero])
                                     / y_true_arr[nonzero])) * 100)
    else:
        mape = 0.0
    return {
        "mae":  round(float(mae)),
        "rmse": round(rmse),
        "r2":   round(float(r2), 3),
        "mape_pct": round(mape, 1),
    }


# ══════════════════════════════════════════════════════════════════
#  CANDIDATE MODELS
# ══════════════════════════════════════════════════════════════════
def _build_candidates() -> dict:
    """Return {name: estimator} for every model to compare."""
    candidates = {
        "LinearRegression": LinearRegression(),
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=120, max_depth=12, min_samples_leaf=3,
            n_jobs=-1, random_state=42,
        ),
        "GradientBoostingRegressor": GradientBoostingRegressor(
            n_estimators=150, max_depth=3, learning_rate=0.08, random_state=42,
        ),
    }
    if _HAS_XGBOOST:
        candidates["XGBRegressor"] = XGBRegressor(
            n_estimators=150, max_depth=5, learning_rate=0.08,
            subsample=0.9, colsample_bytree=0.9, random_state=42,
            verbosity=0,
        )
    return candidates


# ══════════════════════════════════════════════════════════════════
#  TRAINING / MODEL SELECTION
# ══════════════════════════════════════════════════════════════════
def train_model(force: bool = False) -> dict:
    """
    Train & compare all candidate models, automatically select the best
    one (lowest RMSE on the held-out test set), and persist it.

    Returns the `meta` dict (same shape as before, with extra keys):
      - mae, rmse, r2, mape_pct, n_samples, n_train, n_test, importances,
        model_type, n_estimators        (legacy keys, from the SELECTED model)
      - model_comparison: {model_name: {mae, rmse, r2, mape_pct}}
      - selected_model:   name of the chosen model
      - xgboost_available: bool
    """
    global _model_cache, _encoders_cache, _model_meta_cache

    if not force and os.path.exists(MODEL_PATH):
        try:
            with open(MODEL_PATH, "rb") as f:
                bundle = pickle.load(f)
            _model_cache      = bundle["model"]
            _encoders_cache   = bundle["encoders"]
            _model_meta_cache = bundle["meta"]
            return bundle["meta"]
        except Exception:
            logger.exception("Failed to load cached model, retraining from scratch")

    df = pd.read_csv(DATA_PATH)
    df = df.dropna(subset=["prix", "surface", "chambres"])

    for col in ["salles_bain", "etage"]:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())
        else:
            df[col] = 1

    df_enc, encoders = _encode_df(df)

    X = df_enc[FEATURES]
    y = df_enc["prix"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    candidates = _build_candidates()
    comparison = {}
    fitted_models = {}

    for name, estimator in candidates.items():
        try:
            estimator.fit(X_train, y_train)
            y_pred = estimator.predict(X_test)
            comparison[name] = _compute_metrics(y_test, y_pred)
            fitted_models[name] = estimator
        except Exception:
            logger.exception("Training failed for candidate %s", name)

    if not fitted_models:
        raise RuntimeError("No ML model could be trained successfully.")

    # Auto-select best model: lowest RMSE wins
    best_name = min(comparison, key=lambda n: comparison[n]["rmse"])
    best_model = fitted_models[best_name]
    best_metrics = comparison[best_name]

    # Feature importances (tree-based models only — LinearRegression has none)
    if hasattr(best_model, "feature_importances_"):
        importances = dict(zip(FEATURES, np.round(best_model.feature_importances_, 3).tolist()))
    elif hasattr(best_model, "coef_"):
        # Normalize absolute coefficients to a pseudo-importance distribution
        coefs = np.abs(best_model.coef_)
        total = coefs.sum() or 1.0
        importances = dict(zip(FEATURES, np.round(coefs / total, 3).tolist()))
    else:
        importances = {f: 0.0 for f in FEATURES}

    meta = {
        # Legacy keys — always describe the SELECTED model
        "mae":          best_metrics["mae"],
        "rmse":         best_metrics["rmse"],
        "r2":           best_metrics["r2"],
        "mape_pct":     best_metrics["mape_pct"],
        "n_samples":    len(df),
        "n_train":      len(X_train),
        "n_test":       len(X_test),
        "importances":  importances,
        "model_type":   best_name,
        "n_estimators": getattr(best_model, "n_estimators", None),
        # Phase 2 additions
        "model_comparison": comparison,
        "selected_model":   best_name,
        "xgboost_available": _HAS_XGBOOST,
    }

    bundle = {"model": best_model, "encoders": encoders, "meta": meta}
    try:
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(bundle, f)
    except Exception:
        logger.exception("Failed to persist trained model to %s", MODEL_PATH)

    _model_cache      = best_model
    _encoders_cache   = encoders
    _model_meta_cache = meta
    return meta


def _ensure_loaded():
    global _model_cache
    if _model_cache is None:
        train_model()


# ══════════════════════════════════════════════════════════════════
#  PREDICTION  (unchanged public behaviour)
# ══════════════════════════════════════════════════════════════════
def predict_price(ville: str, quartier: str, surface: int, chambres: int,
                   salles_bain: int = 1, etage: int = 2,
                   ascenseur: str = "Yes", parking: str = "No",
                   terrasse: str = "No") -> dict:
    """Predict apartment price and return analysis dict."""
    _ensure_loaded()
    row = pd.DataFrame([{
        "ville": ville, "quartier": quartier,
        "surface": surface, "chambres": chambres,
        "salles_bain": salles_bain, "etage": etage,
        "ascenseur": ascenseur, "parking": parking, "terrasse": terrasse,
    }])
    row_enc = _apply_encoders(row, _encoders_cache)
    predicted = float(_model_cache.predict(row_enc[FEATURES])[0])
    return {"predicted_price": round(predicted)}


def analyze_apartment(apt: dict) -> dict:
    """
    Full price analysis for a single apartment dict.
    Returns predicted price, delta, and deal_quality label.

    NOTE: deal_label text is now plain ASCII (no emoji) so it renders
    correctly in the PDF export (Phase 1 fix). The frontend can still add
    its own emoji/icons for the web UI based on `deal_quality`.
    """
    _ensure_loaded()
    pred = predict_price(
        ville       = apt.get("ville", ""),
        quartier    = apt.get("quartier", ""),
        surface     = int(apt.get("surface", 80)),
        chambres    = int(apt.get("chambres", 2)),
        salles_bain = int(apt.get("salles_bain", 1)),
        etage       = int(apt.get("etage", 2)),
        ascenseur   = str(apt.get("ascenseur", "No")),
        parking     = str(apt.get("parking",   "No")),
        terrasse    = str(apt.get("terrasse",  "No")),
    )
    predicted = pred["predicted_price"]
    actual    = int(apt.get("prix", 0))
    delta     = actual - predicted        # positive = overpriced, negative = good deal
    pct_diff  = round(delta / predicted * 100, 1) if predicted else 0

    if pct_diff <= -10:
        quality = "good_deal"
        label   = "Bonne affaire"
        detail  = f"{abs(pct_diff):.0f}% sous le prix du marché"
    elif pct_diff <= 5:
        quality = "fair"
        label   = "Prix correct"
        detail  = f"Conforme au marché ({pct_diff:+.1f}%)"
    else:
        quality = "overpriced"
        label   = "Surestimé"
        detail  = f"{pct_diff:.0f}% au-dessus du marché"

    return {
        "predicted_price": predicted,
        "actual_price":    actual,
        "delta":           delta,
        "pct_diff":        pct_diff,
        "deal_quality":    quality,
        "deal_label":      label,
        "deal_detail":     detail,
    }


def get_model_meta() -> dict:
    """Return cached model metrics (train if needed)."""
    _ensure_loaded()
    return _model_meta_cache or {}
