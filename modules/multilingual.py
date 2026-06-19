"""
multilingual.py — Feature 7: Multilingual NLP (FR / EN / AR / Darija)
Normalizes prompts from any supported language to French entities.
"""
import re

# ── Language detection keywords ────────────────────────────────────────────────
LANG_SIGNALS = {
    "ar":     ["أريد","شقة","الدار","البيضاء","غرف","ميزانية","مساحة","في","شقق"],
    "darija": ["بغيت","شي","فكازا","فراباط","فطنجة","ديال","دراهم","بيت"],
    "en":     ["apartment","flat","studio","bedroom","budget","surface","looking","need","want","find"],
    "fr":     ["appartement","appart","cherche","budget","chambres","surface","ville"],
}

# ── City translations to canonical French names ────────────────────────────────
CITY_TRANSLATIONS = {
    # Arabic
    "الدار البيضاء": "Casablanca", "الدارالبيضاء": "Casablanca",
    "الرباط": "Rabat",
    "مراكش": "Marrakech",
    "فاس": "Fès", "فاسl": "Fès",
    "طنجة": "Tanger",
    "أكادير": "Agadir",
    # Darija
    "كازا": "Casablanca", "الكازا": "Casablanca",
    "رباط": "Rabat",
    "مراكش": "Marrakech",
    # English
    "casablanca": "Casablanca",
    "rabat": "Rabat",
    "marrakech": "Marrakech",
    "fez": "Fès", "fes": "Fès",
    "tangier": "Tanger", "tanger": "Tanger",
    "agadir": "Agadir",
}

# ── Number translations (Arabic-Indic + words) ─────────────────────────────────
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

NUM_WORDS = {
    # Cardinal numbers (for EN/AR bedrooms count only — NOT budget multipliers)
    "one":"1","two":"2","three":"3","four":"4","five":"5",
    "six":"6","seven":"7","eight":"8","nine":"9","ten":"10",
    # NOTE: "million" and "thousand" intentionally excluded here.
    # Budget regex in extractor.py handles "1 million", "2 millions", "900k" directly.
    "واحد":"1","اثنين":"2","ثلاثة":"3","أربعة":"4","خمسة":"5",
    # Arabic "مليون" translated to French "million" so budget regex can still catch it
    "مليون":"million","ألف":"1000",
}

# ── Translation tables: foreign → French equivalents ──────────────────────────
EN_TO_FR = {
    "apartment":  "appartement", "flat":       "appartement",
    "studio":     "studio",      "house":      "maison",
    "bedroom":    "chambre",     "bedrooms":   "chambres",
    "budget":     "budget",      "surface":    "surface",
    "I need":     "je cherche",  "I want":     "je veux",
    "I am looking for": "je cherche",
    "looking for":"je cherche",
    "in":         "à",
    "square meters":"m²", "sqm":"m²", "sq.m":"m²",
}

AR_TO_FR = {
    "شقة":     "appartement", "شقق":    "appartement",
    "غرف":     "chambres",    "غرفة":   "chambre",
    "ميزانية": "budget",      "مساحة":  "surface",
    "أريد":    "je cherche",  "أبحث عن":"je cherche",
    "في":      "à",           "متر مربع":"m²",
}

DARIJA_TO_FR = {
    "بغيت":   "je cherche",  "شي":     "",
    "appart":  "appartement", "فكازا":  "à Casablanca",
    "فراباط": "à Rabat",     "فطنجة":  "à Tanger",
    "ديال":   "de",           "دراهم":  "MAD",
    "غرف":    "chambres",     "بيت":    "maison",
}


def detect_language(prompt: str) -> str:
    """Detect the dominant language of the prompt."""
    prompt_lower = prompt.lower()
    scores = {lang: 0 for lang in LANG_SIGNALS}
    for lang, signals in LANG_SIGNALS.items():
        for sig in signals:
            if sig in prompt_lower or sig in prompt:
                scores[lang] += 1
    # Darija beats Arabic if both score (it's a superset)
    if scores["darija"] > 0:
        return "darija"
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "fr"


def _replace_dict(text: str, mapping: dict) -> str:
    for src, tgt in mapping.items():
        text = text.replace(src, tgt)
    return text


def _translate_arabic_numbers(text: str) -> str:
    return text.translate(ARABIC_DIGITS)


def _translate_city_names(text: str) -> str:
    for ar_city, fr_city in CITY_TRANSLATIONS.items():
        if ar_city in text:
            text = text.replace(ar_city, fr_city)
    return text


def normalize_to_french(prompt: str) -> tuple[str, str]:
    """
    Translate any supported language prompt into a French-equivalent string
    that the existing NLP extractors can process.

    Returns
    -------
    (normalized_prompt, detected_language)
    """
    lang = detect_language(prompt)

    # Step 1: Arabic-Indic digits → ASCII
    text = _translate_arabic_numbers(prompt)

    # Step 2: City names → French
    text = _translate_city_names(text)

    # Step 3: Domain-specific translations
    if lang == "en":
        text = _replace_dict(text, EN_TO_FR)
    elif lang in ("ar", "darija"):
        text = _replace_dict(text, AR_TO_FR)
        text = _replace_dict(text, DARIJA_TO_FR)

    # Step 4: Numeric word substitution
    for word, num in NUM_WORDS.items():
        text = re.sub(rf"\b{re.escape(word)}\b", num, text, flags=re.IGNORECASE)

    return text.strip(), lang


# ── Self-test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        "Je cherche un appartement à Casa de 90m² avec 3 chambres budget 900000 dh",
        "I need an apartment in Casablanca with 3 bedrooms budget 900k dh",
        "أريد شقة في الدار البيضاء بميزانية 900000 درهم",
        "بغيت شي appart فكازا 3 غرف",
    ]
    for t in tests:
        norm, lang = normalize_to_french(t)
        print(f"[{lang}] {t[:50]!r}")
        print(f"  → {norm[:80]!r}\n")
