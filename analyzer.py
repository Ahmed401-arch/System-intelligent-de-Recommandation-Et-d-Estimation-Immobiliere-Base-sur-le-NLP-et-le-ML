"""
analyzer.py — Phase 2
Missing field detector + question generator + optimized prompt builder.
"""
from extractor import extract_all, validate_budget, validate_chambres, validate_surface, VALIDATION

# ── Field metadata ─────────────────────────────────────────────────────────────
FIELD_META = {
    "city": {
        "label":       "Ville",
        "question":    "Dans quelle ville souhaitez-vous habiter ?",
        "placeholder": "Casablanca, Rabat, Tanger…",
        "type":        "select",
        "options":     ["Casablanca", "Rabat", "Marrakech", "Fès", "Tanger", "Agadir", "Meknès", "Oujda"],
    },
    "budget": {
        "label":       "Budget maximum (MAD)",
        "question":    "Quel est votre budget maximum ?",
        "placeholder": "Ex : 600000 | 900k | 1.5 million",
        "type":        "number",
        "min":         VALIDATION["budget"]["min"],
        "max":         VALIDATION["budget"]["max"],
    },
    "bedrooms": {
        "label":       "Chambres (minimum)",
        "question":    "Combien de chambres souhaitez-vous ?",
        "placeholder": "Ex : 2",
        "type":        "number",
        "min":         VALIDATION["chambres"]["min"],
        "max":         VALIDATION["chambres"]["max"],
    },
    "surface": {
        "label":       "Surface minimum (m²)",
        "question":    "Quelle surface minimale souhaitez-vous ?",
        "placeholder": "Ex : 80",
        "type":        "number",
        "min":         VALIDATION["surface"]["min"],
        "max":         VALIDATION["surface"]["max"],
    },
}


# ══════════════════════════════════════════════════════════════
#  PHASE 2 — MISSING FIELD DETECTION
# ══════════════════════════════════════════════════════════════

def analyze_prompt(prompt: str) -> dict:
    """
    Analyze a natural-language prompt.
    Returns extraction result + field metadata for the UI form.
    """
    result = extract_all(prompt)

    # Build form fields for missing data
    form_fields = []
    for field in result["missing"]:
        meta = FIELD_META.get(field, {})
        form_fields.append({"field": field, **meta})

    # Optional surface field if not detected
    if result["surface"] is None and "surface" not in result["missing"]:
        form_fields.append({"field": "surface", **FIELD_META["surface"]})

    return {
        **result,
        "form_fields": form_fields,
        "is_complete": len(result["missing"]) == 0,
        "questions":   [FIELD_META[f]["question"] for f in result["missing"]],
    }


def validate_form_fields(form_data: dict) -> dict:
    """
    Validate user-supplied form values.
    Returns {field: error_message} for any invalid inputs.
    """
    errors = {}

    if "budget" in form_data and form_data["budget"]:
        ok, _, msg = validate_budget(str(form_data["budget"]))
        if not ok:
            errors["budget"] = msg

    if "bedrooms" in form_data and form_data["bedrooms"]:
        ok, _, msg = validate_chambres(str(form_data["bedrooms"]))
        if not ok:
            errors["bedrooms"] = msg

    if "surface" in form_data and form_data["surface"]:
        ok, _, msg = validate_surface(str(form_data["surface"]))
        if not ok:
            errors["surface"] = msg

    return errors


def build_profile(initial: dict, form_data: dict) -> dict:
    """
    Merge NLP-extracted entities with user-supplied form values.
    Form data wins only when the NLP result was None.
    """
    profile = dict(initial)

    # Coerce and fill
    if not profile.get("city") and form_data.get("city"):
        profile["city"] = str(form_data["city"]).strip()

    if not profile.get("budget") and form_data.get("budget"):
        ok, val, _ = validate_budget(str(form_data["budget"]))
        if ok:
            profile["budget"] = val

    if not profile.get("bedrooms") and form_data.get("bedrooms"):
        ok, val, _ = validate_chambres(str(form_data["bedrooms"]))
        if ok:
            profile["bedrooms"] = val

    if not profile.get("surface") and form_data.get("surface"):
        ok, val, _ = validate_surface(str(form_data["surface"]))
        if ok:
            profile["surface"] = val

    return profile


def build_optimized_prompt(profile: dict) -> str:
    """Build a clean, professional search prompt from the user profile."""
    lines = [f"Je recherche un appartement à {profile.get('city', '—')}."]
    lines.append("")
    lines.append("Critères :")
    if profile.get("budget"):
        lines.append(f"  • Budget maximal   : {profile['budget']:,} MAD")
    if profile.get("surface"):
        lines.append(f"  • Surface minimum  : {profile['surface']} m²")
    if profile.get("bedrooms"):
        lines.append(f"  • Chambres minimum : {profile['bedrooms']}")
    lines.append("")
    lines.append("Veuillez identifier les meilleures options correspondant")
    lines.append("à ces critères dans la base de données disponible.")
    return "\n".join(lines)
