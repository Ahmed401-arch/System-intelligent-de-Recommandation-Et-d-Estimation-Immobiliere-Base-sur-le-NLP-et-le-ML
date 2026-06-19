"""
database.py — SQLite database layer (no ORM needed).
Tables: users · search_history · favorites
"""
import sqlite3, hashlib, secrets, hmac, datetime, os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "app.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    """Create all tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    UNIQUE NOT NULL,
            email       TEXT    UNIQUE NOT NULL,
            password_hash TEXT  NOT NULL,
            role        TEXT    DEFAULT 'user',
            created_at  TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS search_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
            original_query  TEXT,
            optimized_prompt TEXT,
            city            TEXT,
            budget          INTEGER,
            surface         INTEGER,
            bedrooms        INTEGER,
            results_count   INTEGER DEFAULT 0,
            date            TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS favorites (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
            apartment_id INTEGER NOT NULL,
            city         TEXT,
            quartier     TEXT,
            prix         INTEGER,
            surface      INTEGER,
            chambres     INTEGER,
            score        INTEGER DEFAULT 0,
            date_saved   TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, apartment_id)
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
            apartment_id INTEGER NOT NULL,
            liked        INTEGER DEFAULT NULL,   -- 1=like, 0=dislike, NULL=no like/dislike
            rating       INTEGER DEFAULT NULL,   -- 1..5 stars
            date         TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, apartment_id)
        );

        -- Phase 9: indexes for performance on datasets > 10k rows
        CREATE INDEX IF NOT EXISTS idx_history_user_date  ON search_history(user_id, date DESC);
        CREATE INDEX IF NOT EXISTS idx_history_city       ON search_history(city);
        CREATE INDEX IF NOT EXISTS idx_favorites_user     ON favorites(user_id);
        CREATE INDEX IF NOT EXISTS idx_favorites_apt      ON favorites(apartment_id);
        CREATE INDEX IF NOT EXISTS idx_feedback_apt       ON feedback(apartment_id);
        CREATE INDEX IF NOT EXISTS idx_feedback_user      ON feedback(user_id);
    """)
    conn.commit()
    conn.close()

# ── Password helpers ───────────────────────────────────────────────────────────
def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h    = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}${h.hex()}"

def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
        return hmac.compare_digest(h, expected.hex())
    except Exception:
        return False

# ── User CRUD ──────────────────────────────────────────────────────────────────
def user_register(username: str, email: str, password: str) -> dict:
    if len(password) < 6:
        return {"ok": False, "error": "Mot de passe trop court (6 car. min)."}
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO users (username,email,password_hash) VALUES (?,?,?)",
            (username.strip(), email.strip().lower(), _hash_password(password))
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
        conn.close()
        return {"ok": True, "user": dict(user)}
    except sqlite3.IntegrityError as e:
        return {"ok": False, "error": "Nom d'utilisateur ou email déjà utilisé."}

def user_login(email: str, password: str) -> dict:
    conn  = get_conn()
    row   = conn.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    conn.close()
    if not row:
        return {"ok": False, "error": "Email ou mot de passe incorrect."}
    if not _verify_password(password, row["password_hash"]):
        return {"ok": False, "error": "Email ou mot de passe incorrect."}
    return {"ok": True, "user": dict(row)}

def user_get(user_id: int) -> dict | None:
    conn = get_conn()
    row  = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ── Search history ─────────────────────────────────────────────────────────────
def history_add(user_id, query, prompt, profile, results_count=0):
    """Insert a search-history row and COMMIT immediately.

    Defensive: profile may be None or missing keys — never raises.
    """
    profile = profile or {}
    conn = get_conn()
    conn.execute(
        """INSERT INTO search_history
           (user_id,original_query,optimized_prompt,city,budget,surface,bedrooms,results_count)
           VALUES (?,?,?,?,?,?,?,?)""",
        (user_id, query, prompt,
         profile.get("city"), profile.get("budget"),
         profile.get("surface"), profile.get("bedrooms"), results_count)
    )
    conn.commit()
    conn.close()

def history_get(user_id, limit=20, offset=0) -> list:
    """Return the most recent searches first (latest on top), paginated."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM search_history WHERE user_id=? ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def history_count(user_id) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM search_history WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return row["c"] if row else 0

def history_delete(user_id, history_id):
    conn = get_conn()
    conn.execute("DELETE FROM search_history WHERE id=? AND user_id=?", (history_id, user_id))
    conn.commit(); conn.close()

def history_clear(user_id):
    conn = get_conn()
    conn.execute("DELETE FROM search_history WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()

# ── Favorites ──────────────────────────────────────────────────────────────────
def fav_add(user_id, apt: dict) -> dict:
    try:
        conn = get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO favorites
               (user_id,apartment_id,city,quartier,prix,surface,chambres,score)
               VALUES (?,?,?,?,?,?,?,?)""",
            (user_id, apt["id"], apt.get("ville"), apt.get("quartier"),
             apt.get("prix"), apt.get("surface"), apt.get("chambres"), apt.get("score_pct",0))
        )
        conn.commit(); conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def fav_remove(user_id, apartment_id) -> dict:
    conn = get_conn()
    conn.execute("DELETE FROM favorites WHERE user_id=? AND apartment_id=?", (user_id, apartment_id))
    conn.commit(); conn.close()
    return {"ok": True}

def fav_get(user_id) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM favorites WHERE user_id=? ORDER BY date_saved DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def fav_ids(user_id) -> set:
    conn = get_conn()
    rows = conn.execute("SELECT apartment_id FROM favorites WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return {r["apartment_id"] for r in rows}


# ── User AI Profile ────────────────────────────────────────────────────────────
def get_user_profile(user_id: int) -> dict:
    """
    Compute a full AI-driven user profile from their search history and favorites.
    Returns structured profile for dashboard AI insights.
    """
    conn = get_conn()

    # All searches for this user
    searches = conn.execute(
        "SELECT * FROM search_history WHERE user_id=? ORDER BY date DESC",
        (user_id,)
    ).fetchall()
    searches = [dict(r) for r in searches]

    # All favorites
    favs = conn.execute(
        "SELECT * FROM favorites WHERE user_id=? ORDER BY date_saved DESC",
        (user_id,)
    ).fetchall()
    favs = [dict(r) for r in favs]

    conn.close()
    if not searches and not favs:
        return {"has_data": False}

    # ── City preferences ──────────────────────────────────────
    city_counts = {}
    for s in searches:
        c = s.get("city")
        if c:
            city_counts[c] = city_counts.get(c, 0) + 1
    fav_city_counts = {}
    for f in favs:
        c = f.get("city")
        if c:
            fav_city_counts[c] = fav_city_counts.get(c, 0) + 1
    preferred_city = max(city_counts, key=city_counts.get) if city_counts else None

    # ── Budget analysis ───────────────────────────────────────
    budgets = [s["budget"] for s in searches if s.get("budget")]
    fav_prices = [f["prix"] for f in favs if f.get("prix")]
    budget_min = min(budgets) if budgets else None
    budget_max = max(budgets) if budgets else None
    budget_avg = round(sum(budgets) / len(budgets)) if budgets else None
    fav_price_avg = round(sum(fav_prices) / len(fav_prices)) if fav_prices else None

    # ── Surface analysis ──────────────────────────────────────
    surfaces = [s["surface"] for s in searches if s.get("surface")]
    fav_surfaces = [f["surface"] for f in favs if f.get("surface")]
    surface_avg = round(sum(surfaces) / len(surfaces), 1) if surfaces else None
    fav_surface_avg = round(sum(fav_surfaces) / len(fav_surfaces), 1) if fav_surfaces else None

    # ── Bedroom analysis ──────────────────────────────────────
    bedrooms_list = [s["bedrooms"] for s in searches if s.get("bedrooms")]
    fav_bedrooms = [f["chambres"] for f in favs if f.get("chambres")]
    bedrooms_mode = max(set(bedrooms_list), key=bedrooms_list.count) if bedrooms_list else None
    fav_bedrooms_avg = round(sum(fav_bedrooms) / len(fav_bedrooms), 1) if fav_bedrooms else None

    # ── Activity timeline ─────────────────────────────────────
    from collections import defaultdict
    import datetime
    daily = defaultdict(int)
    for s in searches:
        d = (s.get("date") or "")[:10]
        if d:
            daily[d] += 1
    # Last 14 days
    today = datetime.date.today()
    timeline = []
    for i in range(13, -1, -1):
        day = str(today - datetime.timedelta(days=i))
        timeline.append({"date": day, "count": daily.get(day, 0)})

    # ── Search success rate ───────────────────────────────────
    successful = [s for s in searches if s.get("results_count", 0) > 0]
    success_rate = round(len(successful) / len(searches) * 100) if searches else 0

    # ── Behavior score (engagement) ───────────────────────────
    engagement = min(100, len(searches) * 5 + len(favs) * 10)

    # ── City chart data ───────────────────────────────────────
    city_chart = {
        "labels": list(city_counts.keys()),
        "data":   list(city_counts.values()),
    }

    # ── Budget trend (last 10 searches with budget) ───────────
    budget_trend_data = [
        {"date": s["date"][:10], "budget": s["budget"]}
        for s in reversed(searches)
        if s.get("budget")
    ][-10:]

    return {
        "has_data":         True,
        "total_searches":   len(searches),
        "total_favs":       len(favs),
        "success_rate":     success_rate,
        "engagement":       engagement,
        # City
        "preferred_city":   preferred_city,
        "city_counts":      city_counts,
        "fav_city_counts":  fav_city_counts,
        "city_chart":       city_chart,
        # Budget
        "budget_min":       budget_min,
        "budget_max":       budget_max,
        "budget_avg":       budget_avg,
        "fav_price_avg":    fav_price_avg,
        "budget_trend":     budget_trend_data,
        # Surface
        "surface_avg":      surface_avg,
        "fav_surface_avg":  fav_surface_avg,
        # Bedrooms
        "bedrooms_mode":    bedrooms_mode,
        "fav_bedrooms_avg": fav_bedrooms_avg,
        # Timeline
        "timeline":         timeline,
        # Raw for top-N reco
        "recent_searches":  searches[:10],
        "recent_favs":      favs[:5],
    }

# ── Feedback (Phase 4: Like / Dislike / Rating) ─────────────────────────────────
def feedback_set(user_id: int, apartment_id: int, liked: int | None = None,
                  rating: int | None = None) -> dict:
    """
    Upsert a feedback row for (user, apartment).
    `liked`  : 1 = like, 0 = dislike, None = leave unchanged / clear if explicitly passed
    `rating` : 1..5 stars, or None to leave unchanged.
    Only non-None fields are updated; existing values are preserved otherwise.
    """
    if liked is not None and liked not in (0, 1):
        return {"ok": False, "error": "liked doit être 0 ou 1"}
    if rating is not None and not (1 <= int(rating) <= 5):
        return {"ok": False, "error": "rating doit être entre 1 et 5"}

    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM feedback WHERE user_id=? AND apartment_id=?",
        (user_id, apartment_id)
    ).fetchone()

    if existing:
        new_liked  = liked  if liked  is not None else existing["liked"]
        new_rating = rating if rating is not None else existing["rating"]
        conn.execute(
            "UPDATE feedback SET liked=?, rating=?, date=datetime('now') WHERE id=?",
            (new_liked, new_rating, existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO feedback (user_id,apartment_id,liked,rating) VALUES (?,?,?,?)",
            (user_id, apartment_id, liked, rating)
        )
    conn.commit()
    conn.close()
    return {"ok": True}

def feedback_get_for_apartment(apartment_id: int) -> dict:
    """Aggregate like/dislike/rating stats for one apartment."""
    conn = get_conn()
    row = conn.execute(
        """SELECT
             SUM(CASE WHEN liked=1 THEN 1 ELSE 0 END) AS likes,
             SUM(CASE WHEN liked=0 THEN 1 ELSE 0 END) AS dislikes,
             AVG(rating) AS avg_rating,
             COUNT(rating) AS n_ratings
           FROM feedback WHERE apartment_id=?""",
        (apartment_id,)
    ).fetchone()
    conn.close()
    return {
        "likes":      row["likes"] or 0,
        "dislikes":   row["dislikes"] or 0,
        "avg_rating": round(row["avg_rating"], 2) if row["avg_rating"] else None,
        "n_ratings":  row["n_ratings"] or 0,
    }

def feedback_user_get(user_id: int, apartment_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM feedback WHERE user_id=? AND apartment_id=?",
        (user_id, apartment_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def feedback_stats() -> dict:
    """
    Global feedback statistics:
    - most liked apartments
    - average ratings
    - total counts
    """
    conn = get_conn()

    totals = conn.execute(
        """SELECT
             SUM(CASE WHEN liked=1 THEN 1 ELSE 0 END) AS total_likes,
             SUM(CASE WHEN liked=0 THEN 1 ELSE 0 END) AS total_dislikes,
             COUNT(rating) AS total_ratings,
             AVG(rating)   AS overall_avg_rating,
             COUNT(DISTINCT apartment_id) AS apartments_with_feedback
           FROM feedback"""
    ).fetchone()

    most_liked = conn.execute(
        """SELECT apartment_id,
                  SUM(CASE WHEN liked=1 THEN 1 ELSE 0 END) AS likes,
                  AVG(rating) AS avg_rating,
                  COUNT(rating) AS n_ratings
           FROM feedback
           GROUP BY apartment_id
           HAVING likes > 0
           ORDER BY likes DESC, avg_rating DESC
           LIMIT 10"""
    ).fetchall()

    top_rated = conn.execute(
        """SELECT apartment_id, AVG(rating) AS avg_rating, COUNT(rating) AS n_ratings
           FROM feedback
           WHERE rating IS NOT NULL
           GROUP BY apartment_id
           HAVING n_ratings >= 1
           ORDER BY avg_rating DESC, n_ratings DESC
           LIMIT 10"""
    ).fetchall()

    conn.close()
    return {
        "total_likes":              totals["total_likes"] or 0,
        "total_dislikes":           totals["total_dislikes"] or 0,
        "total_ratings":            totals["total_ratings"] or 0,
        "overall_avg_rating":       round(totals["overall_avg_rating"], 2) if totals["overall_avg_rating"] else None,
        "apartments_with_feedback": totals["apartments_with_feedback"] or 0,
        "most_liked": [
            {"apartment_id": r["apartment_id"], "likes": r["likes"],
             "avg_rating": round(r["avg_rating"], 2) if r["avg_rating"] else None,
             "n_ratings": r["n_ratings"]}
            for r in most_liked
        ],
        "top_rated": [
            {"apartment_id": r["apartment_id"],
             "avg_rating": round(r["avg_rating"], 2) if r["avg_rating"] else None,
             "n_ratings": r["n_ratings"]}
            for r in top_rated
        ],
    }

def feedback_bulk_for_apartments(apartment_ids: list[int]) -> dict[int, dict]:
    """Bulk-load feedback aggregates for a list of apartment ids (one query)."""
    if not apartment_ids:
        return {}
    conn = get_conn()
    placeholders = ",".join("?" * len(apartment_ids))
    rows = conn.execute(
        f"""SELECT apartment_id,
                   SUM(CASE WHEN liked=1 THEN 1 ELSE 0 END) AS likes,
                   SUM(CASE WHEN liked=0 THEN 1 ELSE 0 END) AS dislikes,
                   AVG(rating) AS avg_rating,
                   COUNT(rating) AS n_ratings
            FROM feedback
            WHERE apartment_id IN ({placeholders})
            GROUP BY apartment_id""",
        apartment_ids
    ).fetchall()
    conn.close()
    return {
        r["apartment_id"]: {
            "likes": r["likes"] or 0,
            "dislikes": r["dislikes"] or 0,
            "avg_rating": round(r["avg_rating"], 2) if r["avg_rating"] else None,
            "n_ratings": r["n_ratings"] or 0,
        }
        for r in rows
    }


# ── Analytics ──────────────────────────────────────────────────────────────────
def analytics_get() -> dict:
    conn = get_conn()
    def one(sql, *args):
        r = conn.execute(sql, args).fetchone()
        return r[0] if r else 0

    total_searches  = one("SELECT COUNT(*) FROM search_history")
    total_users     = one("SELECT COUNT(*) FROM users")
    total_favorites = one("SELECT COUNT(*) FROM favorites")

    row = conn.execute(
        "SELECT city, COUNT(*) c FROM search_history WHERE city IS NOT NULL GROUP BY city ORDER BY c DESC LIMIT 1"
    ).fetchone()
    top_city = row["city"] if row else "—"

    avg_budget  = one("SELECT AVG(budget)  FROM search_history WHERE budget IS NOT NULL")
    avg_surface = one("SELECT AVG(surface) FROM search_history WHERE surface IS NOT NULL")
    avg_rooms   = one("SELECT AVG(bedrooms) FROM search_history WHERE bedrooms IS NOT NULL")

    cities_rows = conn.execute(
        "SELECT city, COUNT(*) c FROM search_history WHERE city IS NOT NULL GROUP BY city ORDER BY c DESC"
    ).fetchall()
    cities_chart = {"labels": [r["city"] for r in cities_rows], "data": [r["c"] for r in cities_rows]}

    budget_rows = conn.execute(
        "SELECT date(date) d, AVG(budget) avg FROM search_history WHERE budget IS NOT NULL GROUP BY d ORDER BY d DESC LIMIT 14"
    ).fetchall()
    budget_chart = {"labels": [r["d"] for r in reversed(budget_rows)],
                    "data":   [round(r["avg"]) for r in reversed(budget_rows)]}

    daily_rows = conn.execute(
        "SELECT date(date) d, COUNT(*) c FROM search_history GROUP BY d ORDER BY d DESC LIMIT 14"
    ).fetchall()
    daily_chart = {"labels": [r["d"] for r in reversed(daily_rows)],
                   "data":   [r["c"] for r in reversed(daily_rows)]}

    conn.close()
    return {
        "total_searches":  total_searches,
        "total_users":     total_users,
        "total_favorites": total_favorites,
        "top_city":        top_city,
        "avg_budget":      round(avg_budget)  if avg_budget  else 0,
        "avg_surface":     round(avg_surface) if avg_surface else 0,
        "avg_rooms":       round(avg_rooms, 1) if avg_rooms  else 0,
        "cities_chart":    cities_chart,
        "budget_chart":    budget_chart,
        "daily_chart":     daily_chart,
    }
