"""
explainer.py — Phase 8: Explainable AI

Turns the raw scorer.py breakdown (city/budget/surface/bedrooms points) into
human-readable explanations and percentage contributions, e.g.:

    "Sélectionné car il est 12% sous le prix du marché, dispose de 15 m² de
     plus que demandé, et correspond au quartier recherché."

Public API
──────────
  explain_apartment(apt, profile) -> dict
      {
        "contributions": {"budget": 32.6, "surface": 23.9, "bedrooms": 21.7, "location": 30.4},
        "reasons": ["...", "...", ...],   # short bullet reasons (used by PDF + UI)
        "summary": "Sélectionné car ..."  # one human-readable sentence
      }

`apt` is expected to already contain a `breakdown` dict (city/budget/surface/
bedrooms points), as produced by recommender._format / scorer.score_apartment.
If absent, contributions default to 0.
"""
from __future__ import annotations

# Max points per category, must match scorer.py weights.
MAX_POINTS = {"city": 28, "budget": 30, "surface": 22, "bedrooms": 20}


def _pct_contributions(breakdown: dict) -> dict:
    """Convert raw point breakdown into 0-100% contribution per category."""
    total_possible = sum(MAX_POINTS.values()) or 1
    return {
        "location": round(breakdown.get("city", 0) / total_possible * 100, 1),
        "budget":   round(breakdown.get("budget", 0) / total_possible * 100, 1),
        "surface":  round(breakdown.get("surface", 0) / total_possible * 100, 1),
        "bedrooms": round(breakdown.get("bedrooms", 0) / total_possible * 100, 1),
    }


def _budget_reason(apt: dict, profile: dict) -> str | None:
    budget = profile.get("budget")
    price  = apt.get("prix")
    if not budget or not price:
        return None
    diff_pct = round((budget - price) / budget * 100)
    if diff_pct > 0:
        return f"{diff_pct}% sous le prix du marché demandé"
    if diff_pct < 0:
        return f"{abs(diff_pct)}% au-dessus du budget indiqué"
    return "exactement au budget indiqué"


def _surface_reason(apt: dict, profile: dict) -> str | None:
    req_surface = profile.get("surface")
    surface     = apt.get("surface")
    if not surface:
        return None
    if req_surface:
        diff = surface - req_surface
        if diff > 0:
            return f"{diff} m² de plus que demandé"
        if diff < 0:
            return f"{abs(diff)} m² de moins que demandé"
        return "surface exactement conforme à la demande"
    return f"surface de {surface} m²"


def _bedrooms_reason(apt: dict, profile: dict) -> str | None:
    req = profile.get("bedrooms")
    ch  = apt.get("chambres")
    if not ch:
        return None
    if req:
        diff = ch - int(req)
        if diff == 0:
            return f"{ch} chambres, conforme à la demande"
        if diff > 0:
            return f"{ch} chambres ({diff} de plus que demandé)"
        return f"{ch} chambres ({abs(diff)} de moins que demandé)"
    return f"{ch} chambres"


def _location_reason(apt: dict, profile: dict) -> str | None:
    city = profile.get("city")
    if city and str(apt.get("ville", "")).lower() == city.lower():
        return f"correspond au quartier recherché ({apt.get('quartier', city)})"
    if apt.get("ville"):
        return f"situé à {apt['ville']}"
    return None


def explain_apartment(apt: dict, profile: dict) -> dict:
    """
    Build the Explainable AI breakdown for one apartment recommendation.
    """
    breakdown = apt.get("breakdown") or {}
    contributions = _pct_contributions(breakdown)

    reasons = []
    for fn in (_budget_reason, _surface_reason, _bedrooms_reason, _location_reason):
        r = fn(apt, profile)
        if r:
            reasons.append(r)

    if reasons:
        if len(reasons) > 1:
            summary = "Sélectionné car il est " + ", ".join(reasons[:-1]) + f", et {reasons[-1]}."
        else:
            summary = f"Sélectionné car il est {reasons[0]}."
    else:
        summary = "Sélectionné sur la base des critères disponibles."

    return {
        "contributions": contributions,
        "reasons": reasons,
        "summary": summary,
    }


def explain_results(results: list[dict], profile: dict) -> list[dict]:
    """
    Helper for routes: returns a new list where each apartment dict gets an
    added "xai" key with the explanation (contributions/reasons/summary),
    without mutating the caller's `breakdown`/other fields.
    """
    enriched = []
    for apt in results:
        xai = explain_apartment(apt, profile)
        new_apt = dict(apt)
        new_apt["xai"] = xai
        # Keep "reasons" populated for pdf_export.py compatibility if absent
        new_apt.setdefault("reasons", xai["reasons"])
        enriched.append(new_apt)
    return enriched
