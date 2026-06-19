"""
recommender.py  — Priority 2 + 4
Cascading soft-match: always returns top_n results.
Never returns 0 unless the database itself is empty.
"""
import os, pandas as pd
from scorer import score_apartment

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "housing.csv")

def _load_df() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, encoding="utf-8")
    df.columns = [c.strip() for c in df.columns]
    return df

def get_available_cities() -> list[str]:
    return sorted(_load_df()["ville"].dropna().unique().tolist())

def get_city_stats(city: str | None = None) -> dict:
    df = _load_df()
    if city:
        df = df[df["ville"].str.lower() == city.lower()]
    if df.empty:
        return {}
    return {
        "count":        int(len(df)),
        "avg_price":    int(df["prix"].mean()),
        "min_price":    int(df["prix"].min()),
        "max_price":    int(df["prix"].max()),
        "avg_surface":  round(float(df["surface"].mean()), 1),
        "avg_chambres": round(float(df["chambres"].mean()), 1),
    }

def _format(row: dict, profile: dict, is_soft: bool = False, feedback_scores: dict | None = None) -> dict:
    total, breakdown = score_apartment(row, profile)
    budget  = profile.get("budget")
    savings = (budget - row["prix"]) if budget else None
    value   = round(row["surface"] / row["prix"] * 100_000, 1) if row["prix"] else 0
    apt_id  = int(row.get("id", 0))

    feedback_boost = 0.0
    feedback = None
    if feedback_scores:
        fb = feedback_scores.get(apt_id)
        if fb:
            feedback = fb
            # Small additive signal (max ~5 pts): likes and high ratings nudge
            # an apartment up without overpowering the core match score.
            likes    = fb.get("likes", 0) or 0
            dislikes = fb.get("dislikes", 0) or 0
            avg_rating = fb.get("avg_rating")
            feedback_boost += min(3.0, likes * 0.5) - min(3.0, dislikes * 0.5)
            if avg_rating:
                feedback_boost += (avg_rating - 3) * 0.6  # -1.2..+1.2

    return {
        "id":            apt_id,
        "ville":         str(row.get("ville", "")),
        "quartier":      str(row.get("quartier", "")),
        "prix":          int(row.get("prix", 0)),
        "surface":       int(row.get("surface", 0)),
        "chambres":      int(row.get("chambres", 0)),
        "ascenseur":     str(row.get("ascenseur", "No")),
        "parking":       str(row.get("parking",   "No")),
        "terrasse":      str(row.get("terrasse",  "No")),
        "lat":           float(row.get("lat", 0)),
        "lng":           float(row.get("lng", 0)),
        "score":         total,
        "score_pct":     min(100, max(0, total)),
        "breakdown":     breakdown,
        "savings":       int(savings) if savings is not None else 0,
        "value_ratio":   value,
        "is_soft_match": is_soft,
        "feedback":       feedback,
        "_rank_score":    total + feedback_boost,
    }

def _score_and_sort(rows, profile, is_soft=False, feedback_scores=None):
    scored = [_format(r, profile, is_soft, feedback_scores) for r in rows]
    scored.sort(key=lambda x: (x["_rank_score"], x["value_ratio"]), reverse=True)
    for s in scored:
        s.pop("_rank_score", None)
    return scored

def recommend(profile: dict, top_n: int = 5, feedback_scores: dict | None = None) -> dict:
    """
    Cascading filter strategy — 4 passes, each more relaxed than the last.
    Pass 0: strict  (city + budget + bedrooms + surface)
    Pass 1: relax surface
    Pass 2: relax bedrooms ±1  + budget +25%
    Pass 3: relax bedrooms ±2  + budget +50%  (drop surface)
    Pass 4: city only (show what's available)

    `feedback_scores` (Phase 4): optional {apartment_id: {likes, dislikes,
    avg_rating, n_ratings}} dict used as an additional ranking signal.
    """
    df          = _load_df()
    total_db    = len(df)
    city        = profile.get("city")
    budget      = profile.get("budget")
    bedrooms    = int(profile.get("bedrooms") or 0)
    surface     = int(profile.get("surface")  or 0)

    # City base
    city_df = df[df["ville"].str.lower() == city.lower()] if city else df
    strict_count = len(city_df)

    relaxed_msg = None
    is_relaxed  = False

    def _apply(frame, bgt, bdr, srf):
        f = frame.copy()
        if bgt:  f = f[f["prix"]     <= bgt]
        if bdr:  f = f[f["chambres"] >= bdr]
        if srf:  f = f[f["surface"]  >= srf]
        return f

    # Pass 0 — strict
    filtered = _apply(city_df, budget, bedrooms or None, surface or None)
    filtered_count = len(filtered)

    # Pass 1 — drop surface constraint
    if len(filtered) < top_n and surface:
        filtered = _apply(city_df, budget, bedrooms or None, None)
        if len(filtered) >= top_n:
            is_relaxed = True
            relaxed_msg = f"Surface minimum ignorée — {len(filtered)} biens trouvés."

    # Pass 2 — relax bedrooms by 1, budget +25%
    if len(filtered) < top_n:
        b2 = int(budget * 1.25) if budget else None
        d2 = max(1, bedrooms - 1) if bedrooms else None
        filtered = _apply(city_df, b2, d2, None)
        if len(filtered) >= top_n:
            is_relaxed = True
            parts = []
            if b2 and b2 != budget:
                parts.append(f"budget élargi à {b2:,} MAD")
            if d2 and d2 != bedrooms:
                parts.append(f"{d2}+ chambres acceptées")
            relaxed_msg = "Critères assouplis : " + ", ".join(parts) + "."

    # Pass 3 — relax bedrooms by 2, budget +50%
    if len(filtered) < top_n:
        b3 = int(budget * 1.50) if budget else None
        d3 = max(1, bedrooms - 2) if bedrooms else None
        filtered = _apply(city_df, b3, d3, None)
        if len(filtered) >= 1:
            is_relaxed = True
            relaxed_msg = f"Budget élargi à {b3:,} MAD et {d3}+ chambres acceptées."

    # Pass 4 — entire city
    if len(filtered) < top_n:
        filtered = city_df.copy()
        is_relaxed = True
        relaxed_msg = "Tous les biens disponibles dans la ville affichés (critères très éloignés)."

    # Pass 5 — entire DB
    if len(filtered) == 0:
        filtered = df.copy()
        is_relaxed = True
        relaxed_msg = "Base complète utilisée — aucun bien ne correspond aux critères."

    rows   = filtered.to_dict(orient="records")
    scored = _score_and_sort(rows, profile, is_soft=is_relaxed, feedback_scores=feedback_scores)
    top    = scored[:top_n]

    # Plain-text rank labels (no emoji — PDF-safe, Phase 1 fix). The web
    # frontend already renders its own medal emojis client-side based on
    # `rank`, so this field is informational/PDF-facing only.
    rank_labels = {0: "#1", 1: "#2", 2: "#3"}
    for i, apt in enumerate(top):
        apt["rank"]  = i + 1
        apt["medal"] = rank_labels.get(i, f"#{i+1}")

    return {
        "total_before":  total_db,
        "filtered":      filtered_count,    # strict filtered count (for display)
        "results":       top,
        "message":       None,
        "is_relaxed":    is_relaxed,
        "relaxed_msg":   relaxed_msg,
    }
