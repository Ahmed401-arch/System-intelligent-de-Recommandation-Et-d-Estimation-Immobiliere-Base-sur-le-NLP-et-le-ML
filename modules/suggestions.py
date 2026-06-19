"""
suggestions.py — Feature 8: Smart Suggestions
Returns data-driven defaults when user info is minimal.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def get_city_stats(city=None):
    try:
        import pandas as pd
        data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "housing.csv")
        df = pd.read_csv(data_path)
        if city:
            df = df[df["ville"].str.lower() == city.lower()]
        if df.empty:
            return {}
        return {
            "avg_price":   int(df["prix"].mean()),
            "avg_surface": round(float(df["surface"].mean()), 1),
            "avg_chambres":round(float(df["chambres"].mean()), 1),
        }
    except Exception:
        return {}

def get_smart_suggestions(city: str | None, analysis: dict) -> list[dict]:
    """
    Return a list of suggestion dicts: {field, value, label, reason}
    Only suggest fields the user has NOT provided.
    """
    suggestions = []
    stats = get_city_stats(city)
    if not stats:
        return []

    detected = analysis.get("detected", {})

    if not detected.get("budget") and stats.get("avg_price"):
        avg = stats["avg_price"]
        suggestions.append({
            "field":  "budget",
            "value":  avg,
            "label":  f"Budget moyen à {city or 'cette ville'} : {avg:,} MAD",
            "reason": f"Basé sur {stats.get('avg_price',0):,} MAD de moyenne dans la base"
        })

    if not detected.get("surface") and stats.get("avg_surface"):
        avg = stats["avg_surface"]
        suggestions.append({
            "field":  "surface",
            "value":  int(avg),
            "label":  f"Surface typique : {avg} m²",
            "reason": f"Surface médiane des biens disponibles"
        })

    if not detected.get("bedrooms") and stats.get("avg_chambres"):
        avg = round(stats["avg_chambres"])
        suggestions.append({
            "field":  "bedrooms",
            "value":  avg,
            "label":  f"Chambres typiques : {avg}",
            "reason": f"Moyenne des biens dans la base"
        })

    return suggestions
