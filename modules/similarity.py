"""
similarity.py — Phase 3: Similar Apartments Engine

For any apartment (by id), find the Top-N most similar apartments using:
  - K-Nearest Neighbors (cosine metric) over a normalized numeric feature
    space (price, surface, bedrooms, bathrooms, floor, amenities).
  - A cosine-similarity score (0-1, displayed as %) for each match.
  - A human-readable "why similar" explanation comparing the matched
    apartment to the reference on price, surface, location and amenities.

Public API
──────────
  get_similar_apartments(apartment_id, top_n=5) -> dict
      {
        "reference": {...apartment row...},
        "similar": [
            {..apartment fields.., "similarity_pct": 92.4,
             "why": ["même quartier (Maarif)", "surface très proche (+3 m²)", ...]},
            ...
        ]
      }

The model (NearestNeighbors index) is built lazily on first call and cached
in memory, then rebuilt only if housing.csv changes (mtime check) — keeping
this fast even on >10k rows (Phase 9).
"""
import os
import logging

import pandas as pd
import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "housing.csv")

NUMERIC_FEATURES = ["prix", "surface", "chambres", "salles_bain", "etage"]
BINARY_FEATURES  = ["ascenseur", "parking", "terrasse"]

# ── In-memory index cache ───────────────────────────────────────────────────
_cache = {
    "mtime": None,
    "df": None,
    "X": None,
    "scaler": None,
    "knn": None,
}


def _load_and_build():
    """(Re)build the feature matrix + KNN index from housing.csv."""
    mtime = os.path.getmtime(DATA_PATH) if os.path.exists(DATA_PATH) else None

    if _cache["knn"] is not None and _cache["mtime"] == mtime:
        return  # cache still valid

    df = pd.read_csv(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]

    work = df.copy()
    for col in BINARY_FEATURES:
        if col in work.columns:
            work[col + "_enc"] = (work[col].astype(str).str.lower() == "yes").astype(int)
        else:
            work[col + "_enc"] = 0

    for col in NUMERIC_FEATURES:
        if col not in work.columns:
            work[col] = 0
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)

    feature_cols = NUMERIC_FEATURES + [c + "_enc" for c in BINARY_FEATURES]
    scaler = StandardScaler()
    X = scaler.fit_transform(work[feature_cols].values)

    n_neighbors = min(21, len(df))  # self + up to 20 neighbors
    knn = NearestNeighbors(n_neighbors=n_neighbors, metric="cosine")
    knn.fit(X)

    _cache.update(mtime=mtime, df=df, X=X, scaler=scaler, knn=knn)


def _why_similar(ref: dict, other: dict) -> list[str]:
    """Generate short, human-readable reasons why `other` resembles `ref`."""
    reasons = []

    if str(ref.get("ville", "")).lower() == str(other.get("ville", "")).lower():
        if str(ref.get("quartier", "")).lower() == str(other.get("quartier", "")).lower():
            reasons.append(f"même quartier ({other.get('quartier')})")
        else:
            reasons.append(f"même ville ({other.get('ville')})")

    try:
        p_ref, p_other = float(ref.get("prix", 0)), float(other.get("prix", 0))
        if p_ref:
            diff_pct = (p_other - p_ref) / p_ref * 100
            if abs(diff_pct) <= 5:
                reasons.append("prix quasi identique")
            else:
                sign = "plus cher" if diff_pct > 0 else "moins cher"
                reasons.append(f"prix {abs(round(diff_pct))}% {sign}")
    except (TypeError, ValueError, ZeroDivisionError):
        pass

    try:
        s_ref, s_other = float(ref.get("surface", 0)), float(other.get("surface", 0))
        diff = s_other - s_ref
        if abs(diff) <= 5:
            reasons.append("surface très proche")
        else:
            sign = "+" if diff > 0 else ""
            reasons.append(f"surface {sign}{round(diff)} m²")
    except (TypeError, ValueError):
        pass

    if ref.get("chambres") == other.get("chambres"):
        reasons.append(f"même nombre de chambres ({other.get('chambres')})")

    shared_amenities = [
        label for col, label in
        [("ascenseur", "ascenseur"), ("parking", "parking"), ("terrasse", "terrasse")]
        if str(ref.get(col, "")).lower() == "yes" and str(other.get(col, "")).lower() == "yes"
    ]
    if shared_amenities:
        reasons.append("équipements communs : " + ", ".join(shared_amenities))

    return reasons[:5]


def get_similar_apartments(apartment_id: int, top_n: int = 5) -> dict:
    """
    Return the top_n apartments most similar to `apartment_id`, using cosine
    similarity over a KNN index built on price/surface/bedrooms/bathrooms/
    floor/amenities.
    """
    _load_and_build()
    df = _cache["df"]

    matches = df.index[df["id"] == apartment_id].tolist()
    if not matches:
        return {"error": f"Appartement #{apartment_id} introuvable", "reference": None, "similar": []}

    idx = matches[0]
    ref_row = df.iloc[idx]
    ref_dict = ref_row.to_dict()

    X = _cache["X"]
    knn = _cache["knn"]

    # KNN candidate neighbors (cosine distance)
    n_query = min(top_n + 10, X.shape[0])  # over-fetch, then re-rank by cosine sim
    distances, indices = knn.kneighbors(X[idx:idx + 1], n_neighbors=n_query)

    candidate_idx = [i for i in indices[0] if i != idx]

    # Recompute exact cosine similarity for the candidates (KNN cosine
    # "distance" = 1 - similarity, but we recompute directly for clarity).
    sims = cosine_similarity(X[idx:idx + 1], X[candidate_idx])[0]

    ranked = sorted(zip(candidate_idx, sims), key=lambda t: t[1], reverse=True)[:top_n]

    similar = []
    for cand_idx, sim in ranked:
        row = df.iloc[cand_idx].to_dict()
        similar.append({
            "id":            int(row.get("id", 0)),
            "ville":         str(row.get("ville", "")),
            "quartier":      str(row.get("quartier", "")),
            "prix":          int(row.get("prix", 0)),
            "surface":       int(row.get("surface", 0)),
            "chambres":      int(row.get("chambres", 0)),
            "salles_bain":   int(row.get("salles_bain", 0)) if not pd.isna(row.get("salles_bain")) else None,
            "etage":         int(row.get("etage", 0)) if not pd.isna(row.get("etage")) else None,
            "ascenseur":     str(row.get("ascenseur", "No")),
            "parking":       str(row.get("parking", "No")),
            "terrasse":      str(row.get("terrasse", "No")),
            "lat":           float(row.get("lat", 0)) if not pd.isna(row.get("lat")) else None,
            "lng":           float(row.get("lng", 0)) if not pd.isna(row.get("lng")) else None,
            "similarity":    round(float(sim), 4),
            "similarity_pct": round(float(sim) * 100, 1),
            "why":           _why_similar(ref_dict, row),
        })

    return {
        "reference": {
            "id":       int(ref_dict.get("id", 0)),
            "ville":    str(ref_dict.get("ville", "")),
            "quartier": str(ref_dict.get("quartier", "")),
            "prix":     int(ref_dict.get("prix", 0)),
            "surface":  int(ref_dict.get("surface", 0)),
            "chambres": int(ref_dict.get("chambres", 0)),
        },
        "similar": similar,
    }
