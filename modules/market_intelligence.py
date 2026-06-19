"""
market_intelligence.py — Phase 5: Market Intelligence

Advanced market analytics computed from housing.csv:
  - Average price per city
  - Average price per neighborhood (quartier)
  - Average surface per city
  - Average price per square meter (city + neighborhood)
  - Most expensive neighborhoods
  - Cheapest neighborhoods

All functions return plain dict/list structures ready for JSON + Chart.js
(Phase 6) consumption. Results are cached in-memory and rebuilt only if
housing.csv changes (mtime check) — Phase 9 performance optimization.
"""
import os
import logging

import pandas as pd

logger = logging.getLogger(__name__)

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "housing.csv")

_cache = {"mtime": None, "df": None}


def _load_df() -> pd.DataFrame:
    mtime = os.path.getmtime(DATA_PATH) if os.path.exists(DATA_PATH) else None
    if _cache["df"] is not None and _cache["mtime"] == mtime:
        return _cache["df"]

    df = pd.read_csv(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]
    df["prix_m2"] = (df["prix"] / df["surface"]).round(0)

    _cache.update(mtime=mtime, df=df)
    return df


def get_market_overview() -> dict:
    """
    Full market-intelligence payload:
      - price_per_city, surface_per_city, price_per_m2_per_city
      - price_per_neighborhood, price_per_m2_per_neighborhood
      - most_expensive_neighborhoods / cheapest_neighborhoods (top 10 each)
    """
    df = _load_df()

    # ── Per-city aggregates ─────────────────────────────────────────────
    by_city = df.groupby("ville").agg(
        avg_price=("prix", "mean"),
        avg_surface=("surface", "mean"),
        avg_price_m2=("prix_m2", "mean"),
        count=("id", "count"),
    ).reset_index()
    by_city = by_city.sort_values("avg_price", ascending=False)

    price_per_city = {
        "labels": by_city["ville"].tolist(),
        "data":   by_city["avg_price"].round(0).astype(int).tolist(),
    }
    surface_per_city = {
        "labels": by_city["ville"].tolist(),
        "data":   by_city["avg_surface"].round(1).tolist(),
    }
    price_m2_per_city = {
        "labels": by_city["ville"].tolist(),
        "data":   by_city["avg_price_m2"].round(0).astype(int).tolist(),
    }

    # ── Per-neighborhood aggregates ─────────────────────────────────────
    by_quartier = df.groupby(["ville", "quartier"]).agg(
        avg_price=("prix", "mean"),
        avg_surface=("surface", "mean"),
        avg_price_m2=("prix_m2", "mean"),
        count=("id", "count"),
    ).reset_index()

    # Only consider neighborhoods with enough samples for a meaningful average
    reliable = by_quartier[by_quartier["count"] >= 3].copy()

    most_expensive = reliable.sort_values("avg_price", ascending=False).head(10)
    cheapest       = reliable.sort_values("avg_price", ascending=True).head(10)

    def _quartier_records(frame: pd.DataFrame) -> list[dict]:
        return [
            {
                "ville":        r["ville"],
                "quartier":     r["quartier"],
                "avg_price":    int(round(r["avg_price"])),
                "avg_surface":  round(float(r["avg_surface"]), 1),
                "avg_price_m2": int(round(r["avg_price_m2"])),
                "count":        int(r["count"]),
            }
            for _, r in frame.iterrows()
        ]

    price_per_neighborhood = _quartier_records(
        by_quartier.sort_values("avg_price", ascending=False)
    )
    price_m2_per_neighborhood = [
        {
            "ville": r["ville"], "quartier": r["quartier"],
            "avg_price_m2": int(round(r["avg_price_m2"])), "count": int(r["count"]),
        }
        for _, r in by_quartier.sort_values("avg_price_m2", ascending=False).iterrows()
    ]

    return {
        "price_per_city":        price_per_city,
        "surface_per_city":      surface_per_city,
        "price_per_m2_per_city": price_m2_per_city,
        "price_per_neighborhood":    price_per_neighborhood,
        "price_per_m2_per_neighborhood": price_m2_per_neighborhood,
        "most_expensive_neighborhoods": _quartier_records(most_expensive),
        "cheapest_neighborhoods":       _quartier_records(cheapest),
        "city_summary": [
            {
                "ville":        r["ville"],
                "avg_price":    int(round(r["avg_price"])),
                "avg_surface":  round(float(r["avg_surface"]), 1),
                "avg_price_m2": int(round(r["avg_price_m2"])),
                "count":        int(r["count"]),
            }
            for _, r in by_city.iterrows()
        ],
    }


def get_city_market(city: str) -> dict:
    """Market intelligence scoped to a single city (for the apartment-detail / similar view)."""
    df = _load_df()
    city_df = df[df["ville"].str.lower() == city.lower()]
    if city_df.empty:
        return {}

    by_quartier = city_df.groupby("quartier").agg(
        avg_price=("prix", "mean"),
        avg_surface=("surface", "mean"),
        avg_price_m2=("prix_m2", "mean"),
        count=("id", "count"),
    ).reset_index().sort_values("avg_price", ascending=False)

    return {
        "city": city,
        "avg_price":    int(city_df["prix"].mean()),
        "avg_surface":  round(float(city_df["surface"].mean()), 1),
        "avg_price_m2": int(city_df["prix_m2"].mean()),
        "count":        int(len(city_df)),
        "neighborhoods": [
            {
                "quartier":     r["quartier"],
                "avg_price":    int(round(r["avg_price"])),
                "avg_surface":  round(float(r["avg_surface"]), 1),
                "avg_price_m2": int(round(r["avg_price_m2"])),
                "count":        int(r["count"]),
            }
            for _, r in by_quartier.iterrows()
        ],
    }
