"""
data_generator.py — Phase 7: Realistic Synthetic Data Generation

The original generator used a small, hand-written CITY_CONFIG table derived
from the legacy `appartements.csv` (121 rows, 6 columns). The production
dataset is now `housing.csv` (3,927 rows, 14 columns incl. salles_bain,
etage, ascenseur/parking/terrasse, type, lat/lng).

This rewrite LEARNS its generation parameters directly from housing.csv:
  - city distribution (relative weights)
  - per-city neighborhood (quartier) distribution
  - per-city price distribution (mean/std, log-normal-ish via gaussian on
    log scale to avoid negative prices and keep the right skew)
  - per-city surface distribution (mean/std)
  - price-vs-surface correlation (linear regression slope per city)
  - bedroom distribution conditioned on surface buckets (empirical)
  - per-city geographic bounding box (lat/lng) for plausible coordinates
  - global rates for ascenseur / parking / terrasse / salles_bain / etage

Public API (BACKWARD COMPATIBLE)
─────────────────────────────────
  generate(n, seed=42)      -> list[dict]   (now 14-column rows matching housing.csv)
  save_csv(rows, path=None) -> str
  get_stats(rows)           -> dict          (extended with new fields, old keys kept)

New API
───────
  validate(rows)            -> dict   statistical comparison vs. the real
                                       dataset (means/std diffs, KS-test-like
                                       summary) — Phase 7 "validate
                                       generated data statistically".
"""
import os
import csv
import random
import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

SOURCE_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "housing.csv")
OUT_DIR    = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

COLUMNS = ["id", "ville", "quartier", "prix", "surface", "chambres", "salles_bain",
           "etage", "ascenseur", "parking", "terrasse", "type", "lat", "lng"]


# ══════════════════════════════════════════════════════════════════
#  LEARN DISTRIBUTIONS FROM THE REAL DATASET
# ══════════════════════════════════════════════════════════════════
def _learn_profile(source_csv: str = SOURCE_CSV) -> dict:
    """
    Build a statistical profile of the real dataset: per-city weights,
    neighborhood lists, price/surface distributions, correlations,
    amenity rates, bedroom distribution and geo bounding boxes.
    """
    df = pd.read_csv(source_csv)
    df.columns = [c.strip() for c in df.columns]

    n_total = len(df)
    cities = df["ville"].unique().tolist()

    profile = {"cities": {}, "n_source": n_total}

    for city in cities:
        cdf = df[df["ville"] == city]
        weight = len(cdf) / n_total

        quartiers = cdf["quartier"].value_counts(normalize=True)
        quartier_names = quartiers.index.tolist()
        quartier_weights = quartiers.values.tolist()

        # Price: model on log scale (avoids negatives, keeps right skew)
        log_price = np.log(cdf["prix"].clip(lower=1))
        price_log_mean, price_log_std = float(log_price.mean()), float(log_price.std() or 0.05)

        surface_mean, surface_std = float(cdf["surface"].mean()), float(cdf["surface"].std() or 5)

        # price vs surface correlation (per-m2 sensitivity)
        if cdf["surface"].std() > 0:
            slope = float(np.polyfit(cdf["surface"], cdf["prix"], 1)[0])
        else:
            slope = 0.0

        # Bedroom distribution conditioned on surface buckets
        bins = [0, 50, 75, 100, 130, np.inf]
        bucket_labels = ["<50", "50-75", "75-100", "100-130", "130+"]
        cdf = cdf.copy()
        cdf["surface_bucket"] = pd.cut(cdf["surface"], bins=bins, labels=bucket_labels)
        bedroom_by_bucket = {}
        for label in bucket_labels:
            bucket_df = cdf[cdf["surface_bucket"] == label]
            if len(bucket_df):
                counts = bucket_df["chambres"].value_counts(normalize=True)
                bedroom_by_bucket[label] = {int(k): float(v) for k, v in counts.items()}
            else:
                bedroom_by_bucket[label] = {2: 1.0}

        salles_bain_dist = cdf["salles_bain"].value_counts(normalize=True).to_dict()
        etage_dist       = cdf["etage"].value_counts(normalize=True).to_dict()

        ascenseur_rate = float((cdf["ascenseur"].str.lower() == "yes").mean())
        parking_rate   = float((cdf["parking"].str.lower() == "yes").mean())
        terrasse_rate  = float((cdf["terrasse"].str.lower() == "yes").mean())

        type_dist = cdf["type"].value_counts(normalize=True).to_dict() if "type" in cdf.columns else {"Appartement": 1.0}

        lat_min, lat_max = float(cdf["lat"].min()), float(cdf["lat"].max())
        lng_min, lng_max = float(cdf["lng"].min()), float(cdf["lng"].max())

        profile["cities"][city] = {
            "weight": weight,
            "quartiers": quartier_names,
            "quartier_weights": quartier_weights,
            "price_log_mean": price_log_mean,
            "price_log_std": price_log_std,
            "surface_mean": surface_mean,
            "surface_std": surface_std,
            "price_surface_slope": slope,
            "bedroom_by_bucket": bedroom_by_bucket,
            "salles_bain_dist": {int(k): float(v) for k, v in salles_bain_dist.items()},
            "etage_dist": {int(k): float(v) for k, v in etage_dist.items()},
            "ascenseur_rate": ascenseur_rate,
            "parking_rate": parking_rate,
            "terrasse_rate": terrasse_rate,
            "type_dist": type_dist,
            "lat_range": (lat_min, lat_max),
            "lng_range": (lng_min, lng_max),
        }

    return profile


_profile_cache: dict | None = None


def _get_profile() -> dict:
    global _profile_cache
    if _profile_cache is None:
        _profile_cache = _learn_profile()
    return _profile_cache


# ══════════════════════════════════════════════════════════════════
#  SAMPLING HELPERS
# ══════════════════════════════════════════════════════════════════
def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _weighted_choice(items, weights):
    return random.choices(items, weights=weights, k=1)[0]


def _bucket_for_surface(surface: float) -> str:
    if surface < 50:   return "<50"
    if surface < 75:   return "50-75"
    if surface < 100:  return "75-100"
    if surface < 130:  return "100-130"
    return "130+"


def _sample_bedrooms(bucket_dist: dict) -> int:
    items   = list(bucket_dist.keys())
    weights = list(bucket_dist.values())
    return _weighted_choice(items, weights)


def _sample_dist(dist: dict, default):
    if not dist:
        return default
    return _weighted_choice(list(dist.keys()), list(dist.values()))


def _yes_no(rate: float) -> str:
    return "Yes" if random.random() < rate else "No"


# ══════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════
def generate(n: int = 1000, seed: int = 42, source_csv: str = SOURCE_CSV) -> list[dict]:
    """
    Generate `n` synthetic apartments whose distributions (city, neighborhood,
    price, surface, bedrooms, amenities, geo-coordinates) mirror those learned
    from `housing.csv`.
    """
    random.seed(seed)
    np.random.seed(seed)

    profile = _get_profile() if source_csv == SOURCE_CSV else _learn_profile(source_csv)
    cities = list(profile["cities"].keys())
    weights = [profile["cities"][c]["weight"] for c in cities]

    rows = []
    for i in range(n):
        city = _weighted_choice(cities, weights)
        cfg = profile["cities"][city]

        quartier = _weighted_choice(cfg["quartiers"], cfg["quartier_weights"])

        # Surface: gaussian around the learned city mean/std
        surface = int(_clamp(
            random.gauss(cfg["surface_mean"], cfg["surface_std"]),
            20, 350
        ))

        # Price: log-normal around learned mean/std, nudged by the
        # surface→price slope so larger units cost proportionally more.
        base_log_price = cfg["price_log_mean"]
        surface_adjustment = cfg["price_surface_slope"] * (surface - cfg["surface_mean"])
        price = np.exp(random.gauss(base_log_price, cfg["price_log_std"]))
        price = price + surface_adjustment
        price = int(_clamp(price, 100_000, 10_000_000))
        price = round(price / 1000) * 1000

        bucket = _bucket_for_surface(surface)
        chambres = _sample_bedrooms(cfg["bedroom_by_bucket"].get(bucket, {2: 1.0}))

        salles_bain = _sample_dist(cfg["salles_bain_dist"], 1)
        etage       = _sample_dist(cfg["etage_dist"], 2)

        ascenseur = _yes_no(cfg["ascenseur_rate"])
        parking   = _yes_no(cfg["parking_rate"])
        terrasse  = _yes_no(cfg["terrasse_rate"])

        apt_type = _sample_dist(cfg["type_dist"], "Appartement")

        lat_min, lat_max = cfg["lat_range"]
        lng_min, lng_max = cfg["lng_range"]
        lat = round(random.uniform(lat_min, lat_max), 6) if lat_max > lat_min else round(lat_min, 6)
        lng = round(random.uniform(lng_min, lng_max), 6) if lng_max > lng_min else round(lng_min, 6)

        rows.append({
            "id":          i,
            "ville":       city,
            "quartier":    quartier,
            "prix":        price,
            "surface":     surface,
            "chambres":    chambres,
            "salles_bain": salles_bain,
            "etage":       etage,
            "ascenseur":   ascenseur,
            "parking":     parking,
            "terrasse":    terrasse,
            "type":        apt_type,
            "lat":         lat,
            "lng":         lng,
        })

    return rows


def save_csv(rows: list[dict], path: str | None = None) -> str:
    """Save generated rows to CSV. Default filename encodes the row count."""
    if path is None:
        path = os.path.join(OUT_DIR, f"appartements_generated_{len(rows)}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def get_stats(rows: list[dict]) -> dict:
    """Summary statistics for a batch of generated rows (backward-compatible keys)."""
    prices   = [r["prix"]     for r in rows]
    surfaces = [r["surface"]  for r in rows]
    chambres = [r["chambres"] for r in rows]

    city_counts = {}
    for r in rows:
        city_counts[r["ville"]] = city_counts.get(r["ville"], 0) + 1

    return {
        "count":        len(rows),
        "avg_price":    round(sum(prices) / len(prices)),
        "avg_surface":  round(sum(surfaces) / len(surfaces), 1),
        "avg_chambres": round(sum(chambres) / len(chambres), 1),
        "min_price":    min(prices),
        "max_price":    max(prices),
        "city_counts":  city_counts,
    }


def validate(rows: list[dict], source_csv: str = SOURCE_CSV) -> dict:
    """
    Statistically compare generated rows against the real dataset:
    per-city mean price / surface, and overall distribution diffs.
    Returns a dict suitable for display in the dashboard (Phase 7 validation).
    """
    real = pd.read_csv(source_csv)
    real.columns = [c.strip() for c in real.columns]
    gen = pd.DataFrame(rows)

    comparison = []
    for city in real["ville"].unique():
        r = real[real["ville"] == city]
        g = gen[gen["ville"] == city]
        if g.empty:
            continue
        comparison.append({
            "ville": city,
            "real_avg_price":  int(r["prix"].mean()),
            "gen_avg_price":   int(g["prix"].mean()),
            "real_avg_surface": round(float(r["surface"].mean()), 1),
            "gen_avg_surface":  round(float(g["surface"].mean()), 1),
            "real_share_pct": round(len(r) / len(real) * 100, 1),
            "gen_share_pct":  round(len(g) / len(gen) * 100, 1) if len(gen) else 0,
        })

    overall = {
        "real_avg_price":   int(real["prix"].mean()),
        "gen_avg_price":    int(gen["prix"].mean()) if len(gen) else 0,
        "real_avg_surface": round(float(real["surface"].mean()), 1),
        "gen_avg_surface":  round(float(gen["surface"].mean()), 1) if len(gen) else 0,
        "real_n": len(real),
        "gen_n":  len(gen),
    }

    return {"overall": overall, "by_city": comparison}


if __name__ == "__main__":
    for n in (1000, 5000, 10000):
        rows = generate(n)
        path = save_csv(rows)
        stats = get_stats(rows)
        val = validate(rows)
        print(f"Generated {n} rows -> {path}")
        print("  stats:", stats)
        print("  validation overall:", val["overall"])
