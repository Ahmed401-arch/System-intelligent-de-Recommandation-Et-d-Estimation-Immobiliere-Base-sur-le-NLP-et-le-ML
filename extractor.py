"""
extractor.py — Phase 1
NLP Entity Extractor: fuzzy category detection + entity extraction.
Dependencies: stdlib only (difflib, re, unicodedata).
"""

import re
import unicodedata
from difflib import SequenceMatcher, get_close_matches
from typing import Optional

CITY_MAPPING: dict[str, str] = {
    "casa": "Casablanca", "casablanca": "Casablanca", "dar beida": "Casablanca",
    "rabat": "Rabat", "sale": "Rabat", "salé": "Rabat",
    "marrakech": "Marrakech", "marrakesh": "Marrakech", "marrakach": "Marrakech",
    "fes": "Fès", "fez": "Fès", "fès": "Fès", "fass": "Fès",
    "tanger": "Tanger", "tangier": "Tanger", "tanja": "Tanger",
    "agadir": "Agadir",
    "meknes": "Meknès", "meknès": "Meknès", "meknas": "Meknès",
    "oujda": "Oujda", "wujda": "Oujda",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Appartement": [
        "appartement", "appart", "studio", "flat", "logement",
        "apartment", "appartment", "apartement", "appartemnt", "apretment",
    ],
    "Maison":  ["maison", "villa", "riad", "dar", "house", "chalet", "ferme"],
    "Voyage":  ["voyage", "hotel", "hôtel", "destination", "sejour", "travel", "vacances"],
    "Startup": ["startup", "entreprise", "business", "société", "company"],
    "CV":      ["cv", "curriculum", "emploi", "poste", "resume", "candidature"],
}

VALIDATION = {
    "budget":   {"min": 50_000,  "max": 50_000_000},
    "chambres": {"min": 1,        "max": 10},
    "surface":  {"min": 20,       "max": 1_000},
}

_BUDGET_RE = re.compile(
    r"(?:"
    r"(?<!\d)(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:millions?)\b(?!\s*\d)"  # 1 million / 1.5 millions
    r"|(?<!\d)(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*m\b(?!\d|²|2|e)"          # 1m (but not m², m2, metres)
    r"|(\d[\d\s]*)\s*k\b"                                                        # 700k
    r"|(\d[\d\s,]+)\s*(?:mad|dh|dirham|dirhams)"                                # 800000 MAD
    r")",
    re.IGNORECASE,
)
_SURFACE_RE  = re.compile(r"(\d+)\s*m[²2e](?:tres?|tre)?", re.IGNORECASE)
_CHAMBRES_RE = re.compile(r"(\d)\s*(?:chambre|piece|pièce|room)s?|[FT](\d)", re.IGNORECASE)
_FUZZY_THRESHOLD = 0.70


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_ = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_.lower().strip())

def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def detect_category(prompt: str) -> tuple[str, int]:
    norm = _normalize(prompt)
    tokens = re.findall(r"[a-z]+", norm)
    best_cat, best_score = "Autre", 0.0
    for cat, keywords in CATEGORY_KEYWORDS.items():
        norm_kws = [_normalize(k) for k in keywords]
        for kw in norm_kws:
            if kw in norm:
                return cat, 100
        for tok in tokens:
            if len(tok) < 4:
                continue
            for kw in norm_kws:
                s = _sim(tok, kw)
                if s > best_score:
                    best_score, best_cat = s, cat
            close = get_close_matches(tok, norm_kws, n=1, cutoff=_FUZZY_THRESHOLD)
            if close:
                s = _sim(tok, close[0])
                if s > best_score:
                    best_score, best_cat = s, cat
    if best_score >= _FUZZY_THRESHOLD:
        return best_cat, round(best_score * 100)
    return "Autre", round(best_score * 100)


def extract_city(prompt: str) -> Optional[str]:
    norm = _normalize(prompt)
    words = re.findall(r"[a-z]+", norm)
    for word in words:
        if word in CITY_MAPPING:
            return CITY_MAPPING[word]
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    for bg in bigrams:
        if bg in CITY_MAPPING:
            return CITY_MAPPING[bg]
    for word in words:
        if len(word) < 3:
            continue
        close = get_close_matches(word, list(CITY_MAPPING.keys()), n=1, cutoff=0.82)
        if close:
            return CITY_MAPPING[close[0]]
    return None


def extract_budget(prompt: str) -> Optional[int]:
    """
    Extract budget from natural language.
    Groups: 1=million-word, 2=m-suffix, 3=k-suffix, 4=raw+unit
    """
    # Pre-clean: remove nbsp
    text = prompt.replace("\xa0", " ")
    m = _BUDGET_RE.search(text.lower())
    if not m:
        return None
    try:
        raw_clean = lambda s: s.replace(" ", "").replace("\xa0", "")
        if m.group(1):   # "1 million" / "1.5 million"
            return int(float(raw_clean(m.group(1)).replace(",", ".")) * 1_000_000)
        elif m.group(2): # "1m" shorthand
            return int(float(raw_clean(m.group(2)).replace(",", ".")) * 1_000_000)
        elif m.group(3): # "700k"
            return int(raw_clean(m.group(3)).replace(",", "")) * 1_000
        else:            # "800000 MAD"
            return int(raw_clean(m.group(4)).replace(",", ""))
    except (ValueError, TypeError):
        return None


def extract_surface(prompt: str) -> Optional[int]:
    m = _SURFACE_RE.search(prompt)
    if not m:
        return None
    val = int(m.group(1))
    lo, hi = VALIDATION["surface"]["min"], VALIDATION["surface"]["max"]
    return val if lo <= val <= hi else None


def extract_chambres(prompt: str) -> Optional[int]:
    m = _CHAMBRES_RE.search(prompt)
    if not m:
        return None
    val = int(m.group(1) or m.group(2))
    lo, hi = VALIDATION["chambres"]["min"], VALIDATION["chambres"]["max"]
    return val if lo <= val <= hi else None


def extract_all(prompt: str) -> dict:
    category, confidence = detect_category(prompt)
    city     = extract_city(prompt)
    budget   = extract_budget(prompt)
    surface  = extract_surface(prompt)
    chambres = extract_chambres(prompt)
    values   = {"city": city, "budget": budget, "bedrooms": chambres}
    missing  = [f for f in ("city", "budget", "bedrooms") if not values[f]]
    return {
        "category":   category,
        "confidence": confidence,
        "city":       city,
        "budget":     budget,
        "surface":    surface,
        "bedrooms":   chambres,
        "missing":    missing,
        "detected":   {k: (v is not None) for k, v in
                       {"city": city, "budget": budget, "bedrooms": chambres, "surface": surface}.items()},
    }


def validate_budget(raw: str) -> tuple[bool, Optional[int], str]:
    parsed = extract_budget(raw)
    if parsed is None:
        cleaned = re.sub(r"[^\d]", "", raw)
        if cleaned.isdigit():
            parsed = int(cleaned)
    if parsed is None:
        return False, None, "Format non reconnu. Exemples : 600000 | 900k | 1.5 million"
    lo, hi = VALIDATION["budget"]["min"], VALIDATION["budget"]["max"]
    if parsed < lo:
        return False, None, f"Budget trop faible. Minimum : {lo:,} MAD"
    if parsed > hi:
        return False, None, f"Budget trop élevé. Maximum : {hi:,} MAD"
    return True, parsed, ""

def validate_chambres(raw: str) -> tuple[bool, Optional[int], str]:
    parsed = extract_chambres(raw)
    if parsed is None:
        cleaned = re.sub(r"[^\d]", "", raw)
        if cleaned.isdigit():
            parsed = int(cleaned)
    if parsed is None:
        return False, None, "Entrez un nombre entre 1 et 10."
    lo, hi = VALIDATION["chambres"]["min"], VALIDATION["chambres"]["max"]
    if not (lo <= parsed <= hi):
        return False, None, f"Valeur hors limites : {lo} à {hi} chambres."
    return True, parsed, ""

def validate_surface(raw: str) -> tuple[bool, Optional[int], str]:
    parsed = extract_surface(raw)
    if parsed is None:
        cleaned = re.sub(r"[^\d]", "", raw)
        if cleaned.isdigit():
            parsed = int(cleaned)
    if parsed is None:
        return False, None, "Format non reconnu. Exemples : 80 | 90m² | 120 m2"
    lo, hi = VALIDATION["surface"]["min"], VALIDATION["surface"]["max"]
    if not (lo <= parsed <= hi):
        return False, None, f"Surface hors limites : {lo} à {hi} m²."
    return True, parsed, ""
