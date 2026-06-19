"""
main.py — ApartmentAI PFE — Complete Flask Application
Wires all 12 features: Auth · History · Favorites · Explainable AI ·
Dashboard · Map · Multilingual · Suggestions · PDF · Data Generator ·
Advanced Scoring · Professional UI

PHASE 10 — added logging + environment-based configuration.
"""
import os, sys, json, logging
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "modules"))

from flask import (Flask, request, jsonify, render_template,
                   session, redirect, url_for, send_file)
import io

from extractor   import extract_all
from analyzer    import analyze_prompt, build_profile, build_optimized_prompt, validate_form_fields
from recommender import recommend, get_available_cities, get_city_stats
from modules.database    import (init_db, user_register, user_login, user_get,
                                  history_add, history_get, history_delete, history_clear, history_count,
                                  fav_add, fav_remove, fav_get, fav_ids, analytics_get,
                                  feedback_set, feedback_get_for_apartment, feedback_user_get,
                                  feedback_stats, feedback_bulk_for_apartments)
from modules.pdf_export  import generate_pdf
from modules.multilingual import normalize_to_french
from modules.suggestions  import get_smart_suggestions
from modules.data_generator import generate, save_csv, get_stats, validate as validate_generated
from modules.similarity import get_similar_apartments
from modules.market_intelligence import get_market_overview, get_city_market
from modules.explainer import explain_results, explain_apartment

# ══════════════════════════════════════════════════════════════
#  LOGGING (Phase 10)
# ══════════════════════════════════════════════════════════════
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


app = Flask(__name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder  =os.path.join(os.path.dirname(__file__), "static"))
app.secret_key = os.environ.get("SECRET_KEY", "appart-ai-pfe-2025-secret")

init_db()

# ══════════════════════════════════════════════════════════════
#  AUTH HELPERS
# ══════════════════════════════════════════════════════════════
def current_user():
    uid = session.get("user_id")
    return user_get(uid) if uid else None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Connexion requise", "redirect": "/login"}), 401
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════════════════════════
@app.get("/")
def index():
    return render_template("index.html", user=current_user())

@app.get("/login")
def login_page():
    if session.get("user_id"):
        return redirect("/")
    return render_template("login.html")

@app.get("/register")
def register_page():
    if session.get("user_id"):
        return redirect("/")
    return render_template("register.html")

@app.get("/dashboard")
def dashboard_page():
    user = current_user()
    if not user:
        return redirect("/login")
    return render_template("dashboard.html", user=user)

@app.get("/history")
def history_page():
    user = current_user()
    if not user:
        return redirect("/login")
    return render_template("history.html", user=user)

@app.get("/favorites")
def favorites_page():
    user = current_user()
    if not user:
        return redirect("/login")
    return render_template("favorites.html", user=user)

@app.get("/map")
def map_page():
    return render_template("map.html", user=current_user())

@app.get("/admin")
def admin_page():
    user = current_user()
    if not user or user.get("role") != "admin":
        return redirect("/")
    return render_template("admin.html", user=user)

# ══════════════════════════════════════════════════════════════
#  AUTH API
# ══════════════════════════════════════════════════════════════
@app.post("/api/auth/register")
def api_register():
    d = request.get_json(silent=True) or {}
    username = (d.get("username") or "").strip()
    email    = (d.get("email")    or "").strip()
    password = (d.get("password") or "").strip()
    if not all([username, email, password]):
        return jsonify({"error": "Tous les champs sont requis."}), 400
    result = user_register(username, email, password)
    if not result["ok"]:
        return jsonify({"error": result["error"]}), 409
    user = result["user"]
    session["user_id"]   = user["id"]
    session["username"]  = user["username"]
    return jsonify({"ok": True, "username": user["username"]})

@app.post("/api/auth/login")
def api_login():
    d = request.get_json(silent=True) or {}
    result = user_login(d.get("email",""), d.get("password",""))
    if not result["ok"]:
        return jsonify({"error": result["error"]}), 401
    user = result["user"]
    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    return jsonify({"ok": True, "username": user["username"], "role": user.get("role","user")})

@app.post("/api/auth/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})

@app.get("/api/auth/me")
def api_me():
    user = current_user()
    if not user:
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "username": user["username"],
                    "email": user["email"], "role": user.get("role","user")})

# ══════════════════════════════════════════════════════════════
#  CORE NLP API
# ══════════════════════════════════════════════════════════════
@app.get("/api/cities")
def api_cities():
    return jsonify(get_available_cities())

@app.post("/api/analyze")
def api_analyze():
    body   = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "Le champ 'prompt' est requis."}), 400

    # Feature 7: multilingual normalization
    normalized, lang = normalize_to_french(prompt)
    result = analyze_prompt(normalized)
    result["detected_language"] = lang
    result["original_prompt"]   = prompt
    result["normalized_prompt"] = normalized

    # Feature 8: smart suggestions
    result["suggestions"] = get_smart_suggestions(result.get("city"), result)

    return jsonify(result)

@app.post("/api/complete-profile")
def api_complete_profile():
    body      = request.get_json(silent=True) or {}
    initial   = body.get("initial", {})
    form_data = body.get("form_data", {})
    if not initial and not form_data:
        return jsonify({"error": "Données manquantes."}), 400
    errors = validate_form_fields(form_data)
    if errors:
        return jsonify({"errors": errors}), 422
    profile = build_profile(initial, form_data)
    prompt  = build_optimized_prompt(profile)
    return jsonify({
        "profile":          profile,
        "optimized_prompt": prompt,
        "ready": bool(profile.get("city") and profile.get("budget") and profile.get("bedrooms")),
    })

@app.post("/api/recommend")
def api_recommend():
    body    = request.get_json(silent=True) or {}
    profile = body.get("profile", {})
    top_n   = int(body.get("top_n", 5))
    query   = body.get("original_query", "")
    opt_prompt = body.get("optimized_prompt", "")
    if not profile:
        return jsonify({"error": "Profil manquant."}), 400

    # Phase 4: feedback as an additional ranking signal — bulk-load feedback
    # for the candidate city's apartments (cheap single query).
    try:
        city_df_ids = []
        if profile.get("city"):
            from recommender import _load_df
            df = _load_df()
            city_df_ids = df[df["ville"].str.lower() == profile["city"].lower()]["id"].astype(int).tolist()
        feedback_scores = feedback_bulk_for_apartments(city_df_ids) if city_df_ids else {}
    except Exception:
        logger.exception("Impossible de charger les scores de feedback")
        feedback_scores = {}

    result = recommend(profile, top_n=top_n, feedback_scores=feedback_scores)

    # Phase 8: Explainable AI — budget/surface/bedrooms/location contributions
    if result.get("results"):
        result["results"] = explain_results(result["results"], profile)

    # Feature 2: save search to history if logged in
    user_id = session.get("user_id")
    if user_id and result.get("results"):
        history_add(user_id, query, opt_prompt, profile, len(result["results"]))

    # Mark favorites for logged-in users
    if user_id:
        favs = fav_ids(user_id)
        for apt in result.get("results", []):
            apt["is_favorite"] = apt["id"] in favs

    return jsonify(result)

@app.get("/api/city-stats")
def api_city_stats():
    city = request.args.get("city")
    return jsonify(get_city_stats(city))

# ══════════════════════════════════════════════════════════════
#  HISTORY API (Feature 2)
# ══════════════════════════════════════════════════════════════
@app.get("/api/history")
@login_required
def api_history():
    uid  = session["user_id"]
    try:
        page  = max(1, int(request.args.get("page", 1)))
        limit = min(100, max(1, int(request.args.get("limit", 20))))
    except (TypeError, ValueError):
        page, limit = 1, 20
    offset = (page - 1) * limit
    rows  = history_get(uid, limit=limit, offset=offset)
    total = history_count(uid)
    return jsonify({
        "items": rows,
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": (total + limit - 1) // limit if limit else 1,
    })

@app.delete("/api/history/<int:hid>")
@login_required
def api_history_delete(hid):
    history_delete(session["user_id"], hid)
    return jsonify({"ok": True})

@app.delete("/api/history")
@login_required
def api_history_clear():
    history_clear(session["user_id"])
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════════════════
#  FAVORITES API (Feature 3)
# ══════════════════════════════════════════════════════════════
@app.post("/api/favorites")
@login_required
def api_fav_add():
    apt = request.get_json(silent=True) or {}
    result = fav_add(session["user_id"], apt)
    return jsonify(result), (200 if result["ok"] else 400)

@app.delete("/api/favorites/<int:apt_id>")
@login_required
def api_fav_remove(apt_id):
    fav_remove(session["user_id"], apt_id)
    return jsonify({"ok": True})

@app.get("/api/favorites")
@login_required
def api_fav_list():
    return jsonify(fav_get(session["user_id"]))

# ══════════════════════════════════════════════════════════════
#  SIMILAR APARTMENTS API (Phase 3)
# ══════════════════════════════════════════════════════════════
@app.get("/api/similar/<int:apartment_id>")
def api_similar(apartment_id):
    try:
        top_n = min(20, max(1, int(request.args.get("top_n", 5))))
    except (TypeError, ValueError):
        top_n = 5
    try:
        result = get_similar_apartments(apartment_id, top_n=top_n)
        if result.get("error"):
            return jsonify(result), 404

        # Enrich each similar apartment with feedback aggregates (Phase 4)
        ids = [a["id"] for a in result["similar"]]
        fb_map = feedback_bulk_for_apartments(ids)
        for a in result["similar"]:
            a["feedback"] = fb_map.get(a["id"], {"likes": 0, "dislikes": 0, "avg_rating": None, "n_ratings": 0})

        return jsonify(result)
    except Exception as e:
        logger.exception("Erreur calcul appartements similaires")
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════════════════════════
#  USER FEEDBACK API (Phase 4: Like / Dislike / Rating)
# ══════════════════════════════════════════════════════════════
@app.post("/api/feedback/<int:apartment_id>")
@login_required
def api_feedback_set(apartment_id):
    body = request.get_json(silent=True) or {}
    liked  = body.get("liked")    # 1, 0, or null
    rating = body.get("rating")   # 1..5 or null

    if liked is not None:
        try:
            liked = int(liked)
        except (TypeError, ValueError):
            return jsonify({"error": "liked doit être 0 ou 1"}), 400
    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return jsonify({"error": "rating doit être un entier entre 1 et 5"}), 400

    result = feedback_set(session["user_id"], apartment_id, liked=liked, rating=rating)
    if not result["ok"]:
        return jsonify(result), 400

    aggregate = feedback_get_for_apartment(apartment_id)
    return jsonify({"ok": True, "feedback": aggregate})

@app.get("/api/feedback/<int:apartment_id>")
def api_feedback_get(apartment_id):
    aggregate = feedback_get_for_apartment(apartment_id)
    user = current_user()
    if user:
        aggregate["my_feedback"] = feedback_user_get(user["id"], apartment_id)
    return jsonify(aggregate)

@app.get("/api/feedback-stats")
def api_feedback_stats():
    return jsonify(feedback_stats())

# ══════════════════════════════════════════════════════════════
#  MARKET INTELLIGENCE API (Phase 5)
# ══════════════════════════════════════════════════════════════
@app.get("/api/market-intelligence")
def api_market_intelligence():
    try:
        return jsonify(get_market_overview())
    except Exception as e:
        logger.exception("Erreur market intelligence")
        return jsonify({"error": str(e)}), 500

@app.get("/api/market-intelligence/<city_name>")
def api_market_intelligence_city(city_name):
    try:
        data = get_city_market(city_name)
        if not data:
            return jsonify({"error": f"Aucune donnée pour {city_name}"}), 404
        return jsonify(data)
    except Exception as e:
        logger.exception("Erreur market intelligence ville")
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════════════════════════
#  MAP API (Feature 6)
# ══════════════════════════════════════════════════════════════
@app.get("/api/map-data")
def api_map_data():
    import pandas as pd
    data_path = os.path.join(os.path.dirname(__file__), "data", "housing.csv")
    df = pd.read_csv(data_path)
    city = request.args.get("city")
    if city:
        df = df[df["ville"].str.lower() == city.lower()]
    limit = int(request.args.get("limit", 200))
    df = df.head(limit)
    return jsonify(df[["id","ville","quartier","prix","surface","chambres",
                        "ascenseur","parking","terrasse","lat","lng","type"]].to_dict(orient="records"))

# ══════════════════════════════════════════════════════════════
#  PDF EXPORT API (Feature 9)
# ══════════════════════════════════════════════════════════════
@app.post("/api/export-pdf")
def api_export_pdf():
    try:
        body = request.get_json(silent=True) or {}
        profile    = body.get("profile", {})
        results    = body.get("results", [])
        query      = body.get("original_query", "")
        opt_prompt = body.get("optimized_prompt", "")
        pdf_bytes  = generate_pdf(profile, results, query, opt_prompt)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="rapport_appartements.pdf",
        )
    except Exception:
        logger.exception("Échec de l'export PDF")
        return jsonify({"error": "Erreur lors de la génération du PDF. Veuillez réessayer."}), 500

# ══════════════════════════════════════════════════════════════
#  ANALYTICS API (Feature 5)
# ══════════════════════════════════════════════════════════════
@app.get("/api/analytics")
def api_analytics():
    return jsonify(analytics_get())

# ══════════════════════════════════════════════════════════════
#  DATA GENERATOR API (Feature 10)
# ══════════════════════════════════════════════════════════════
@app.post("/api/generate-data")
@login_required
def api_generate_data():
    try:
        body = request.get_json(silent=True) or {}
        n = int(body.get("n", 1000))
        if n not in (1000, 5000, 10000):
            n = min(max(n, 100), 10000)  # allow custom sizes too, clamp 100..10000
        rows = generate(n)
        path = save_csv(rows)
        stats = get_stats(rows)
        validation = validate_generated(rows)
        return jsonify({
            "ok": True,
            "generated": n,
            "path": os.path.basename(path),
            "stats": stats,
            "validation": validation,
        })
    except Exception as e:
        logger.exception("Échec de la génération de données synthétiques")
        return jsonify({"ok": False, "error": str(e)}), 500



# ══════════════════════════════════════════════════════════════
#  AI DASHBOARD API
# ══════════════════════════════════════════════════════════════
@app.get("/api/dashboard")
def api_dashboard():
    """
    Returns full AI-driven dashboard payload:
    - User profile + behavior analysis
    - Smart recommendations based on search history
    - ML model insights
    - Activity timeline
    """
    import pandas as pd
    user = current_user()
    if not user:
        return jsonify({"error": "Non authentifié"}), 401

    uid = user["id"]

    # 1. User behavioral profile
    from modules.database import get_user_profile
    profile_data = get_user_profile(uid)

    # 2. ML model info
    try:
        from modules.ml_model import get_model_meta, train_model, analyze_apartment
        ml_meta = get_model_meta()
        if not ml_meta:
            ml_meta = train_model()
    except Exception:
        ml_meta = {}

    # 3. Smart top recommendations based on user's inferred profile
    top_recs = []
    if profile_data.get("has_data"):
        inferred_profile = {
            "city":     profile_data.get("preferred_city"),
            "budget":   profile_data.get("budget_avg"),
            "surface":  profile_data.get("surface_avg"),
            "bedrooms": profile_data.get("bedrooms_mode"),
        }
        # Only recommend if we have meaningful profile data
        if inferred_profile.get("city") or inferred_profile.get("budget"):
            from recommender import recommend
            rec_result = recommend(inferred_profile, top_n=3)
            # Enrich with ML
            for apt in rec_result.get("results", []):
                try:
                    ml = analyze_apartment(apt)
                    apt.update({
                        "ml_predicted_price": ml["predicted_price"],
                        "ml_deal_label":      ml["deal_label"],
                        "ml_deal_quality":    ml["deal_quality"],
                        "ml_pct_diff":        ml["pct_diff"],
                    })
                except Exception:
                    pass
            top_recs = rec_result.get("results", [])

    # 4. City market stats for preferred city
    market_stats = {}
    city = profile_data.get("preferred_city")
    if city:
        from recommender import get_city_stats
        market_stats = get_city_stats(city)

    # 5. AI Smart Insights (rule-based, fully local)
    insights = _compute_insights(profile_data, market_stats)

    return jsonify({
        "user_profile":  profile_data,
        "top_recs":      top_recs,
        "market_stats":  market_stats,
        "ml_meta":       ml_meta,
        "insights":      insights,
    })


def _compute_insights(profile: dict, market: dict) -> list[dict]:
    """
    Generate AI-style textual insights from local data only.
    Rule-based engine — no external API.
    """
    if not profile.get("has_data"):
        return []

    insights = []
    budget_avg = profile.get("budget_avg")
    market_avg = market.get("avg_price")
    city       = profile.get("preferred_city")
    success    = profile.get("success_rate", 0)
    searches   = profile.get("total_searches", 0)
    favs       = profile.get("total_favs", 0)

    # Budget vs market insight
    if budget_avg and market_avg and city:
        diff_pct = round((budget_avg - market_avg) / market_avg * 100)
        if diff_pct < -20:
            insights.append({
                "type": "warning",
                "icon": "⚠️",
                "title": "Budget inférieur au marché",
                "text":  f"Votre budget moyen ({budget_avg:,} MAD) est {abs(diff_pct)}% "
                         f"sous le prix moyen à {city} ({market_avg:,} MAD). "
                         f"Envisagez d'élargir votre budget ou de regarder des villes moins chères.",
            })
        elif diff_pct > 20:
            insights.append({
                "type": "success",
                "icon": "💡",
                "title": "Fort pouvoir d'achat",
                "text":  f"Votre budget ({budget_avg:,} MAD) dépasse de {diff_pct}% "
                         f"le prix moyen à {city}. Vous pouvez viser des biens premium.",
            })
        else:
            insights.append({
                "type": "info",
                "icon": "✅",
                "title": "Budget aligné au marché",
                "text":  f"Votre budget est aligné au marché de {city} "
                         f"(écart de {diff_pct:+}%). Bonne base de recherche.",
            })

    # Success rate insight
    if searches >= 3:
        if success < 40:
            insights.append({
                "type": "warning",
                "icon": "🔍",
                "title": "Critères trop restrictifs",
                "text":  f"Seulement {success}% de vos recherches retournent des résultats stricts. "
                         f"Le système active le mode assoupli automatiquement.",
            })
        elif success >= 80:
            insights.append({
                "type": "success",
                "icon": "🎯",
                "title": "Critères bien calibrés",
                "text":  f"{success}% de vos recherches retournent des résultats. Vos critères sont réalistes.",
            })

    # Favorite vs search insight
    if searches > 0 and favs > 0:
        ratio = round(favs / searches * 100)
        if ratio >= 30:
            insights.append({
                "type": "info",
                "icon": "❤️",
                "title": "Utilisateur très actif",
                "text":  f"Vous sauvegardez {ratio}% des biens que vous consultez. "
                         f"Votre profil de préférences est très précis.",
            })

    # City diversity insight
    city_counts = profile.get("city_counts", {})
    if len(city_counts) >= 3:
        insights.append({
            "type": "info",
            "icon": "🗺️",
            "title": "Exploration multi-villes",
            "text":  f"Vous avez recherché dans {len(city_counts)} villes différentes. "
                     f"Ville préférée : {city or '—'}.",
        })

    # Activity trend insight
    timeline = profile.get("timeline", [])
    recent_7  = sum(t["count"] for t in timeline[-7:])
    previous_7 = sum(t["count"] for t in timeline[:7])
    if recent_7 > previous_7 * 1.5 and previous_7 > 0:
        insights.append({
            "type": "success",
            "icon": "📈",
            "title": "Activité en hausse",
            "text":  f"Vos recherches ont augmenté de {round((recent_7/previous_7-1)*100)}% "
                     f"ces 7 derniers jours.",
        })

    return insights[:5]   # max 5 insights

# ══════════════════════════════════════════════════════════════
#  MACHINE LEARNING API (Feature 6)
# ══════════════════════════════════════════════════════════════
@app.post("/api/predict")
def api_predict():
    body = request.get_json(silent=True) or {}
    apt  = body.get("apartment", body)
    if not apt:
        return jsonify({"error": "Donnees manquantes"}), 400
    try:
        from modules.ml_model import analyze_apartment
        result = analyze_apartment(apt)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/model-info")
def api_model_info():
    try:
        from modules.ml_model import get_model_meta, train_model
        meta = get_model_meta()
        if not meta:
            meta = train_model()
        return jsonify(meta)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/recommend-ml")
def api_recommend_ml():
    """Recommend + enrich with ML price prediction + return city apts for map."""
    import pandas as pd
    body    = request.get_json(silent=True) or {}
    profile = body.get("profile", {})
    top_n   = int(body.get("top_n", 5))
    if not profile:
        return jsonify({"error": "Profil manquant"}), 400

    rec = recommend(profile, top_n=top_n)

    # Enrich with ML
    try:
        from modules.ml_model import analyze_apartment, get_model_meta, train_model
        if not get_model_meta():
            train_model()
        for apt in rec.get("results", []):
            try:
                ml = analyze_apartment(apt)
                apt.update({
                    "ml_predicted_price": ml["predicted_price"],
                    "ml_delta":           ml["delta"],
                    "ml_pct_diff":        ml["pct_diff"],
                    "ml_deal_quality":    ml["deal_quality"],
                    "ml_deal_label":      ml["deal_label"],
                    "ml_deal_detail":     ml["deal_detail"],
                })
            except Exception:
                pass
    except Exception:
        pass

    # Priority 5: all city apartments for map
    data_path = os.path.join(os.path.dirname(__file__), "data", "housing.csv")
    df = pd.read_csv(data_path)
    city = profile.get("city")
    if city:
        df = df[df["ville"].str.lower() == city.lower()]
    top_ids = [a["id"] for a in rec.get("results", [])]
    city_cols = ["id","ville","quartier","prix","surface","chambres","ascenseur","parking","lat","lng"]
    rec["city_apts"] = df[city_cols].head(300).to_dict(orient="records")
    rec["top_ids"]   = top_ids
    return jsonify(rec)

@app.get("/api/map-city/<city_name>")
def api_map_city(city_name):
    import pandas as pd
    data_path = os.path.join(os.path.dirname(__file__), "data", "housing.csv")
    df = pd.read_csv(data_path)
    df = df[df["ville"].str.lower() == city_name.lower()]
    cols = ["id","ville","quartier","prix","surface","chambres","ascenseur","parking","terrasse","lat","lng"]
    return jsonify(df[cols].to_dict(orient="records"))

# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
#  ML ANALYTICS DASHBOARD API
# ══════════════════════════════════════════════════════════════
@app.get("/api/ml-dashboard")
def api_ml_dashboard():
    """
    Returns complete ML dashboard payload computed from local data only.
    Includes: model metrics, feature importances, scatter data,
    error histogram, business insights, XAI breakdown.
    """
    import pickle, numpy as np, pandas as pd
    from sklearn.model_selection import train_test_split

    data_path  = os.path.join(os.path.dirname(__file__), "data", "housing.csv")
    model_path = os.path.join(os.path.dirname(__file__), "data", "price_model.pkl")

    # 1. Load or train model
    from modules.ml_model import get_model_meta, train_model
    meta = get_model_meta()
    if not meta:
        meta = train_model()

    # 2. Load model bundle for predictions
    try:
        with open(model_path, "rb") as f:
            bundle = pickle.load(f)
        model    = bundle["model"]
        encoders = bundle["encoders"]
    except Exception as e:
        return jsonify({"error": f"Modele non disponible: {str(e)}"}), 500

    # 3. Load and prepare dataset
    df = pd.read_csv(data_path)
    for col in ["ascenseur", "parking", "terrasse"]:
        df[col + "_enc"] = (df[col].str.lower() == "yes").astype(int)
    for col in ["ville", "quartier"]:
        le = encoders[col]
        df[col] = df[col].astype(str).apply(
            lambda x: le.transform([x])[0] if x in le.classes_ else 0
        )

    FEATURES = ["ville", "quartier", "surface", "chambres", "salles_bain",
                "etage", "ascenseur_enc", "parking_enc", "terrasse_enc"]
    X = df[FEATURES]
    y = df["prix"]

    # 4. Re-generate test split (same seed = same split)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    y_pred = model.predict(X_test)
    errors = (y_pred - y_test.values).tolist()

    # 5. Scatter plot — sample 120 points
    import random as rnd
    rnd.seed(42)
    n = min(120, len(y_test))
    idx = rnd.sample(range(len(y_test)), n)
    scatter = {
        "actual":    [int(y_test.values[i]) for i in idx],
        "predicted": [int(y_pred[i])        for i in idx],
    }

    # 6. Error histogram — 20 bins
    counts, edges = np.histogram(errors, bins=20)
    histogram = {
        "counts": counts.tolist(),
        "edges":  [round(e) for e in edges.tolist()],
        "labels": [f"{round(edges[i]/1000)}k" for i in range(len(edges)-1)],
        "mean_error": round(float(np.mean(errors))),
        "std_error":  round(float(np.std(errors))),
        "pct_over":   round(sum(1 for e in errors if e > 0) / len(errors) * 100, 1),
        "pct_under":  round(sum(1 for e in errors if e < 0) / len(errors) * 100, 1),
    }

    # 7. Feature importances (clean names)
    FEAT_LABELS = {
        "surface":      "Surface (m²)",
        "salles_bain":  "Salles de bain",
        "chambres":     "Chambres",
        "etage":        "Etage",
        "ville":        "Ville",
        "terrasse_enc": "Terrasse",
        "quartier":     "Quartier",
        "parking_enc":  "Parking",
        "ascenseur_enc":"Ascenseur",
    }
    raw_imp = meta.get("importances", {})
    importances_sorted = sorted(
        [{"feature": FEAT_LABELS.get(k, k), "key": k, "importance": round(v * 100, 1)}
         for k, v in raw_imp.items()],
        key=lambda x: x["importance"], reverse=True
    )

    # 8. Business insights from raw CSV (before encoding)
    df_raw = pd.read_csv(data_path)
    city_counts = df_raw["ville"].value_counts().to_dict()
    price_by_city = df_raw.groupby("ville")["prix"].mean().round(0).astype(int).to_dict()

    business = {
        "avg_price":          int(df_raw["prix"].mean()),
        "median_price":       int(df_raw["prix"].median()),
        "avg_surface":        round(float(df_raw["surface"].mean()), 1),
        "avg_chambres":       round(float(df_raw["chambres"].mean()), 1),
        "n_cities":           int(df_raw["ville"].nunique()),
        "n_biens":            int(len(df_raw)),
        "city_counts":        city_counts,
        "price_by_city":      price_by_city,
        "top_feature":        importances_sorted[0]["feature"] if importances_sorted else "—",
        "top_feature_pct":    importances_sorted[0]["importance"] if importances_sorted else 0,
        "chambres_dist":      df_raw["chambres"].value_counts().sort_index().to_dict(),
        "pct_ascenseur":      round(df_raw["ascenseur"].str.lower().eq("yes").mean() * 100, 1),
        "pct_parking":        round(df_raw["parking"].str.lower().eq("yes").mean() * 100, 1),
        "pct_terrasse":       round(df_raw["terrasse"].str.lower().eq("yes").mean() * 100, 1),
    }

    # 9. XAI grouped features
    xai_groups = [
        {"label": "Surface habitable", "pct": raw_imp.get("surface", 0) * 100},
        {"label": "Salles de bain",    "pct": raw_imp.get("salles_bain", 0) * 100},
        {"label": "Chambres",          "pct": raw_imp.get("chambres", 0) * 100},
        {"label": "Etage",             "pct": raw_imp.get("etage", 0) * 100},
        {"label": "Localisation",      "pct": (raw_imp.get("ville", 0) + raw_imp.get("quartier", 0)) * 100},
        {"label": "Equipements",       "pct": (raw_imp.get("ascenseur_enc", 0) + raw_imp.get("parking_enc", 0) + raw_imp.get("terrasse_enc", 0)) * 100},
    ]
    for g in xai_groups:
        g["pct"] = round(g["pct"], 1)

    # 10. Market intelligence summary (Phase 5/6)
    try:
        market = get_market_overview()
    except Exception:
        logger.exception("Erreur calcul market intelligence pour le dashboard ML")
        market = {}

    return jsonify({
        "meta":         meta,
        "scatter":      scatter,
        "histogram":    histogram,
        "importances":  importances_sorted,
        "business":     business,
        "xai_groups":   xai_groups,
        # Phase 2: model comparison table (MAE/RMSE/R2/MAPE per candidate)
        "model_comparison":  meta.get("model_comparison", {}),
        "selected_model":    meta.get("selected_model"),
        "xgboost_available": meta.get("xgboost_available", False),
        # Phase 5/6: market intelligence for charts
        "market": market,
    })

@app.get("/ml-dashboard")
def page_ml_dashboard():
    return render_template("ml_dashboard.html")

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", 5000))
    logger.info("Starting ApartmentAI PFE on port %d (debug=%s)", port, debug_mode)
    print("\nApartmentAI PFE — http://localhost:%d" % port)
    print("   NLP - Fuzzy - Multilingual - Recommendation - Explainable AI")
    print("   Map - ML Price Prediction - Auth - History - Favorites - PDF\n")
    app.run(debug=debug_mode, host="0.0.0.0", port=port)
