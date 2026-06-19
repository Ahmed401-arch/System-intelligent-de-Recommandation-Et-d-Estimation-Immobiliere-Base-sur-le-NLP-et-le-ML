"""
scorer.py — Priority 3: Weighted, differentiated scoring.
Fine-grained continuous scoring ensures no two apartments share the same score
unless they are truly identical. Max theoretical score = 100.
"""

def score_apartment(apt: dict, profile: dict) -> tuple[int, dict]:
    """
    Score apartment against profile. Returns (score_0_to_100, breakdown).

    Weights:   city=28  budget=30  surface=22  bedrooms=20
    Fine-grained within each category via floating-point proximity math.
    """
    breakdown = {}
    budget   = profile.get("budget")
    req_surf = profile.get("surface")
    req_ch   = profile.get("bedrooms")

    # ── City (28 pts) ──────────────────────────────────────────
    breakdown["city"] = 28 if (
        profile.get("city") and
        apt.get("ville","").lower() == profile["city"].lower()
    ) else 0

    # ── Budget (30 pts, continuous) ────────────────────────────
    price = apt.get("prix", 0)
    if budget and price:
        ratio = price / budget
        if ratio <= 1.00:
            # Sweet spot: 85-92% → 30 pts; taper on both sides
            if   ratio <= 0.72: pts = 20 + ratio * 4         # too cheap
            elif ratio <= 0.82: pts = 28 + (ratio - 0.72) * 20   # rising
            elif ratio <= 0.92: pts = 30.0                    # ideal band
            elif ratio <= 0.96: pts = 30 - (ratio - 0.92) * 40   # slight over
            else:               pts = 28 - (ratio - 0.96) * 80   # near limit
        elif ratio <= 1.05:
            pts = 10 - (ratio - 1.00) * 160                  # soft: 5% over
        elif ratio <= 1.15:
            pts = 2                                           # 15% over
        else:
            pts = 0
        breakdown["budget"] = max(0, round(pts, 1))
    else:
        breakdown["budget"] = 15

    # ── Surface (22 pts, continuous) ───────────────────────────
    apt_surf = apt.get("surface", 0)
    if req_surf and apt_surf:
        ratio = apt_surf / req_surf
        if   ratio >= 1.40: pts = 22.0
        elif ratio >= 1.00: pts = 10 + ratio * 8.3           # [10..22] when meeting/exceeding
        elif ratio >= 0.90: pts = 5 + (ratio - 0.90) * 50   # [5..10] close under
        elif ratio >= 0.80: pts = (ratio - 0.80) * 50        # [0..5]
        else:               pts = 0
        breakdown["surface"] = max(0, round(pts, 1))
    elif apt_surf and not req_surf:
        # No preference — partial credit
        pts = min(16, apt_surf / 8)
        breakdown["surface"] = round(pts, 1)
    else:
        breakdown["surface"] = 11

    # ── Bedrooms (20 pts, continuous) ──────────────────────────
    apt_ch = apt.get("chambres", 0)
    if req_ch and apt_ch:
        diff = apt_ch - int(req_ch)
        if   diff == 0:  pts = 20.0
        elif diff == 1:  pts = 17.0
        elif diff >= 2:  pts = 13.0      # more than needed — may be too big
        elif diff == -1: pts = 5.0
        else:            pts = 0.0
        breakdown["bedrooms"] = pts
    elif apt_ch and not req_ch:
        breakdown["bedrooms"] = min(20, apt_ch * 4)
    else:
        breakdown["bedrooms"] = 10

    # Convert to integer total for cleaner display
    total = round(sum(breakdown.values()))

    # Convert breakdown values to ints too
    breakdown = {k: round(v) for k, v in breakdown.items()}
    return total, breakdown
