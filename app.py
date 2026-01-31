import os
import re
import json
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from flask import (
    Flask, g, redirect, render_template, request, url_for,
    flash, abort, session, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------- DB config ----------
DATABASE_URL = os.environ.get("DATABASE_URL")  # Render Postgres
IS_PG = bool(DATABASE_URL)

if IS_PG:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.errors import UniqueViolation

APP_TITLE = "MyTube"
DB_PATH = os.environ.get("MYTUBE_DB", "mytube.db")  # SQLite fallback lokalt

# Main admin (låst)
ADMIN_USERNAME = os.environ.get("MYTUBE_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("MYTUBE_ADMIN_PASS", "admin")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")


# ---------- Small SQL helpers ----------
def q(sqlite_sql: str, pg_sql: str) -> str:
    """Pick SQL depending on engine."""
    return pg_sql if IS_PG else sqlite_sql


def dt(col: str) -> str:
    """Datetime cast for ordering (created_at stored as ISO string)."""
    # SQLite: datetime(created_at)
    # Postgres: created_at::timestamp (works for ISO8601 strings)
    return f"{col}::timestamp" if IS_PG else f"datetime({col})"


def like_op() -> str:
    # SQLite LIKE is case-insensitive by default for ASCII; Postgres LIKE is case-sensitive.
    # To behave more similar: use ILIKE on Postgres.
    return "ILIKE" if IS_PG else "LIKE"


def is_unique_violation(exc: Exception) -> bool:
    if IS_PG and isinstance(exc, UniqueViolation):
        return True
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    return False


# ---------- i18n ----------
SUPPORTED_LANGS = ("sv", "en")
I18N = {
    "sv": {
        "nav_history": "Historik",
        "nav_admin": "Adminpanel",
        "nav_users": "Users",
        "search_placeholder": "Sök…",
        "search_btn": "Sök",
        "logout": "Logga ut",
        "signin": "Logga in",
        "views": "visningar",
        "likes": "likes",

        "index_title": "Video-galleri",
        "index_empty": "Inga videos ännu. (Admin lägger till via Adminpanel.)",

        "filter_all": "Alla",
        "filter_sort": "Sortera",
        "sort_new": "Nyast",
        "sort_views": "Mest tittade",
        "sort_likes": "Mest likeade",
        "filter_category": "Kategori",

        "like_btn": "👍 Gilla",
        "liked_btn": "👍 Gillad",
        "open_original": "Öppna original",
        "comments_title": "Kommentarer",
        "name_optional": "Namn (valfritt)",
        "name_placeholder": "Om du är inloggad används ditt username automatiskt",
        "comment_label": "Kommentar",
        "comment_placeholder": "Skriv något…",
        "post_btn": "Posta",

        "login_title": "Logga in",
        "username_label": "Användarnamn",
        "password_label": "Lösenord",
        "login_btn": "Logga in",
        "no_account": "Har du inget konto?",
        "create_account": "Skapa konto",

        "register_title": "Skapa konto",
        "username_placeholder_example": "t.ex. ali123",
        "repeat_password_label": "Upprepa lösenord",
        "create_btn": "Skapa",

        "history_title": "Historik",
        "history_empty": "Din historik är tom.",
        "last_watched": "Senast",
        "watch_count": "Antal gånger",

        "admin_title": "Adminpanel",
        "admin_add_link": "+ Lägg till video",
        "admin_empty": "Inga videos ännu.",
        "admin_delete_confirm": "Ta bort videon?",
        "delete_btn": "Ta bort",
        "edit_btn": "Edit",
        "video_added": "Video tillagd.",
        "video_deleted": "Video borttagen.",
        "video_updated": "Video uppdaterad.",

        "admin_add_title": "Admin: Lägg till video",
        "title_label_req": "Titel*",
        "description_label": "Beskrivning",
        "video_url_label_req": "Video-URL*",
        "video_url_placeholder_admin": "Klistra in Reddit/YouTube/TikTok/Vimeo/Loom-länk",
        "thumb_url_label": "Thumbnail URL (valfritt)",
        "thumb_url_placeholder": "https://… (bild)",
        "save_btn": "Spara",
        "provider_label": "Provider",
        "provider_auto": "Auto (rekommenderas)",
        "provider_youtube": "YouTube",
        "provider_reddit": "Reddit",
        "provider_tiktok": "TikTok",
        "provider_vimeo": "Vimeo",
        "provider_loom": "Loom",
        "provider_custom": "Custom",
        "category_label": "Kategori (valfritt)",
        "category_placeholder": "Ex: Motivation, Cars, Andrew Tate…",
        "reddit_tip": "Tips: För Reddit/TikTok, klistra helst in post-länken.",

        "users_title": "Användare",
        "users_empty": "Inga användare hittades.",
        "edit": "Ändra",
        "locked": "Låst",
        "user_edit_title": "Ändra användare",
        "new_username": "Nytt username",
        "new_password": "Nytt lösenord",
        "make_admin": "Admin?",
        "save_changes": "Spara ändringar",
        "leave_blank_pw": "Lämna lösenord tomt om du inte vill ändra.",
        "main_admin_locked": "Det här är huvudkontot (admin:admin) och får inte ändras.",

        "up_next": "Rekommenderat",
        "recommended_empty": "Inga rekommenderade videos just nu.",

        "playlist_title": "Spellista",
        "playlist_sidebar": "Spellista",
        "playlist_empty_sidebar": "Spellistan är tom.",
        "playlist_none": "Ingen spellista",
        "playlist_create": "Skapa ny spellista",
        "playlist_name": "Spellista namn",
        "playlist_position": "Position i spellistan",

        "next_in_playlist": "Next in playlist",
        "autonext": "Auto-next",
        "autonext_in": "Auto hoppar om {sec}s",

        "must_login": "Du måste logga in först.",
        "bad_login": "Fel användarnamn eller lösenord.",
        "logged_in_as": "Inloggad som {username}.",
        "logged_out": "Utloggad.",
        "register_required": "Användarnamn och lösenord krävs.",
        "passwords_no_match": "Lösenorden matchar inte.",
        "username_reserved": "Det användarnamnet är reserverat.",
        "username_exists": "Användarnamnet finns redan.",
        "account_created": "Konto skapat! Logga in nu.",
        "comment_empty": "Kommentaren kan inte vara tom.",
        "comment_posted": "Kommentar postad.",
        "admin_need_title_url": "Titel och videolänk krävs.",
        "anon": "Anonym",
        "empty_url": "Tom URL",
        "user_updated": "Användare uppdaterad.",
        "cannot_edit_main_admin": "Du kan inte ändra huvudkontot admin.",
        "like_failed": "Kunde inte gilla videon.",
        "like_requires_login": "Du måste vara inloggad för att gilla (1 gång).",
    },
    "en": {
        "nav_history": "History",
        "nav_admin": "Admin",
        "nav_users": "Users",
        "search_placeholder": "Search…",
        "search_btn": "Search",
        "logout": "Logout",
        "signin": "Sign in",
        "views": "views",
        "likes": "likes",

        "index_title": "Video gallery",
        "index_empty": "No videos yet. (Admin adds videos via Admin.)",

        "filter_all": "All",
        "filter_sort": "Sort",
        "sort_new": "Newest",
        "sort_views": "Most viewed",
        "sort_likes": "Most liked",
        "filter_category": "Category",

        "like_btn": "👍 Like",
        "liked_btn": "👍 Liked",
        "open_original": "Open original",
        "comments_title": "Comments",
        "name_optional": "Name (optional)",
        "name_placeholder": "If you're signed in, your username is used automatically",
        "comment_label": "Comment",
        "comment_placeholder": "Write something…",
        "post_btn": "Post",

        "login_title": "Sign in",
        "username_label": "Username",
        "password_label": "Password",
        "login_btn": "Sign in",
        "no_account": "Don't have an account?",
        "create_account": "Create account",

        "register_title": "Create account",
        "username_placeholder_example": "e.g. ali123",
        "repeat_password_label": "Repeat password",
        "create_btn": "Create",

        "history_title": "History",
        "history_empty": "Your history is empty.",
        "last_watched": "Last watched",
        "watch_count": "Times watched",

        "admin_title": "Admin",
        "admin_add_link": "+ Add video",
        "admin_empty": "No videos yet.",
        "admin_delete_confirm": "Delete this video?",
        "delete_btn": "Delete",
        "edit_btn": "Edit",
        "video_added": "Video added.",
        "video_deleted": "Video deleted.",
        "video_updated": "Video updated.",

        "admin_add_title": "Admin: Add video",
        "title_label_req": "Title*",
        "description_label": "Description",
        "video_url_label_req": "Video URL*",
        "video_url_placeholder_admin": "Paste a Reddit/YouTube/TikTok/Vimeo/Loom link",
        "thumb_url_label": "Thumbnail URL (optional)",
        "thumb_url_placeholder": "https://… (image)",
        "save_btn": "Save",
        "provider_label": "Provider",
        "provider_auto": "Auto (recommended)",
        "provider_youtube": "YouTube",
        "provider_reddit": "Reddit",
        "provider_tiktok": "TikTok",
        "provider_vimeo": "Vimeo",
        "provider_loom": "Loom",
        "provider_custom": "Custom",
        "category_label": "Category (optional)",
        "category_placeholder": "Ex: Motivation, Cars, Andrew Tate…",
        "reddit_tip": "Tip: For Reddit/TikTok, paste the post link.",

        "users_title": "Users",
        "users_empty": "No users found.",
        "edit": "Edit",
        "locked": "Locked",
        "user_edit_title": "Edit user",
        "new_username": "New username",
        "new_password": "New password",
        "make_admin": "Admin?",
        "save_changes": "Save changes",
        "leave_blank_pw": "Leave password empty if you don't want to change it.",
        "main_admin_locked": "This is the main admin account and cannot be changed.",

        "up_next": "Recommended",
        "recommended_empty": "No recommendations right now.",

        "playlist_title": "Playlist",
        "playlist_sidebar": "Playlist",
        "playlist_empty_sidebar": "Playlist is empty.",
        "playlist_none": "No playlist",
        "playlist_create": "Create new playlist",
        "playlist_name": "Playlist name",
        "playlist_position": "Position in playlist",

        "next_in_playlist": "Next in playlist",
        "autonext": "Auto-next",
        "autonext_in": "Auto jumps in {sec}s",

        "must_login": "You must sign in first.",
        "bad_login": "Wrong username or password.",
        "logged_in_as": "Signed in as {username}.",
        "logged_out": "Signed out.",
        "register_required": "Username and password are required.",
        "passwords_no_match": "Passwords do not match.",
        "username_reserved": "That username is reserved.",
        "username_exists": "That username already exists.",
        "account_created": "Account created! Please sign in.",
        "comment_empty": "Comment cannot be empty.",
        "comment_posted": "Comment posted.",
        "admin_need_title_url": "Title and video URL are required.",
        "anon": "Anonymous",
        "empty_url": "Empty URL",
        "user_updated": "User updated.",
        "cannot_edit_main_admin": "You cannot edit the main admin account.",
        "like_failed": "Could not like the video.",
        "like_requires_login": "You must be signed in to like (once).",
    },
}


def get_lang() -> str:
    lang = (session.get("lang") or "sv").lower()
    return lang if lang in SUPPORTED_LANGS else "sv"


def t(key: str, **kwargs) -> str:
    lang = get_lang()
    text = I18N.get(lang, {}).get(key) or I18N["sv"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


# ---------- DB ----------
def get_db():
    if "db" not in g:
        if IS_PG:
            # Postgres
            g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            # SQLite
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _ensure_column_sqlite(db, table: str, col: str, ddl: str):
    # SQLite-only migration helper
    cols = [r["name"] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        db.execute(ddl)
        db.commit()


def init_db():
    db = get_db()

    if IS_PG:
        # ---- Postgres schema ----
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            source_url TEXT NOT NULL,
            embed_url TEXT NOT NULL,
            thumbnail_url TEXT DEFAULT '',
            provider TEXT DEFAULT 'custom',
            created_at TEXT NOT NULL,
            views INTEGER NOT NULL DEFAULT 0,
            likes INTEGER NOT NULL DEFAULT 0,
            embed_html TEXT DEFAULT '',
            category TEXT DEFAULT ''
        );
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS watch_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            last_watched_at TEXT NOT NULL,
            watch_count INTEGER NOT NULL DEFAULT 1,
            UNIQUE(user_id, video_id)
        );
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS playlist_items (
            id SERIAL PRIMARY KEY,
            playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 1,
            UNIQUE(playlist_id, video_id)
        );
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS video_likes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, video_id)
        );
        """)

        db.execute("CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);")
        db.execute("CREATE INDEX IF NOT EXISTS idx_comments_video ON comments(video_id);")
        db.execute("CREATE INDEX IF NOT EXISTS idx_history_user_time ON watch_history(user_id, last_watched_at);")
        db.execute("CREATE INDEX IF NOT EXISTS idx_playlist_pos ON playlist_items(playlist_id, position);")

        db.commit()

        admin = db.execute("SELECT id FROM users WHERE username=%s", (ADMIN_USERNAME,)).fetchone()
        if not admin:
            db.execute(
                "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (%s, %s, %s, %s)",
                (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD), 1, datetime.utcnow().isoformat()),
            )
            db.commit()

    else:
        # ---- SQLite schema (din original) ----
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                source_url TEXT NOT NULL,
                embed_url TEXT NOT NULL,
                thumbnail_url TEXT DEFAULT '',
                provider TEXT DEFAULT 'custom',
                created_at TEXT NOT NULL,
                views INTEGER NOT NULL DEFAULT 0,
                likes INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL,
                user_id INTEGER,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS watch_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                last_watched_at TEXT NOT NULL,
                watch_count INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, video_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS playlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 1,
                UNIQUE(playlist_id, video_id),
                FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS video_likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, video_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);
            CREATE INDEX IF NOT EXISTS idx_comments_video ON comments(video_id);
            CREATE INDEX IF NOT EXISTS idx_history_user_time ON watch_history(user_id, last_watched_at);
            CREATE INDEX IF NOT EXISTS idx_playlist_pos ON playlist_items(playlist_id, position);
            """
        )
        db.commit()

        _ensure_column_sqlite(db, "videos", "embed_html", "ALTER TABLE videos ADD COLUMN embed_html TEXT DEFAULT '';")
        _ensure_column_sqlite(db, "videos", "category", "ALTER TABLE videos ADD COLUMN category TEXT DEFAULT '';")

        admin = db.execute("SELECT id FROM users WHERE username=?", (ADMIN_USERNAME,)).fetchone()
        if not admin:
            db.execute(
                "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)",
                (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD), 1, datetime.utcnow().isoformat()),
            )
            db.commit()


@app.before_request
def _ensure_db():
    init_db()


# ---------- Auth helpers ----------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    return db.execute(
        q(
            "SELECT id, username, is_admin FROM users WHERE id=?",
            "SELECT id, username, is_admin FROM users WHERE id=%s",
        ),
        (uid,),
    ).fetchone()


def require_login():
    flash(t("must_login"), "error")
    return redirect(url_for("login", next=request.path))


def require_admin():
    user = current_user()
    if not user or not user["is_admin"]:
        abort(403)


@app.context_processor
def inject_globals():
    return {"app_title": APP_TITLE, "me": current_user(), "t": t, "lang": get_lang()}


@app.route("/lang/<lang_code>")
def set_lang(lang_code: str):
    code = (lang_code or "").lower()
    if code not in SUPPORTED_LANGS:
        code = "sv"
    session["lang"] = code
    nxt = request.args.get("next") or request.referrer or url_for("index")
    return redirect(nxt)


# ---------- oEmbed helpers ----------
def reddit_oembed_html(post_url: str):
    try:
        api = "https://www.reddit.com/oembed?url=" + urllib.parse.quote(post_url, safe="")
        req = urllib.request.Request(api, headers={"User-Agent": "MyTube/1.0 (oembed)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("html")
    except Exception:
        return None


def tiktok_oembed_html(post_url: str):
    try:
        api = "https://www.tiktok.com/oembed?url=" + urllib.parse.quote(post_url, safe="")
        req = urllib.request.Request(api, headers={"User-Agent": "MyTube/1.0 (oembed)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("html")
    except Exception:
        return None


# ---------- URL -> embed conversion ----------
def normalize_embed(source_url: str):
    url = (source_url or "").strip()
    if not url:
        raise ValueError(t("empty_url"))

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if "reddit.com" in host or "redd.it" in host:
        return ("reddit", url)
    if "tiktok.com" in host:
        return ("tiktok", url)

    if "youtube.com" in host:
        qs = parse_qs(parsed.query)
        vid = (qs.get("v") or [None])[0]
        if not vid:
            m = re.search(r"/shorts/([^/?]+)", parsed.path or "")
            vid = m.group(1) if m else None
        if vid:
            return ("youtube", f"https://www.youtube.com/embed/{vid}")

    if "youtu.be" in host:
        vid = (parsed.path or "").strip("/").split("/")[0]
        if vid:
            return ("youtube", f"https://www.youtube.com/embed/{vid}")

    if "vimeo.com" in host:
        m = re.search(r"/(\d+)", parsed.path or "")
        if m:
            vid = m.group(1)
            return ("vimeo", f"https://player.vimeo.com/video/{vid}")

    if "loom.com" in host:
        m = re.search(r"/share/([^/?]+)", parsed.path or "")
        if m:
            vid = m.group(1)
            return ("loom", f"https://www.loom.com/embed/{vid}")

    return ("custom", url)


def force_provider_embed(provider_choice: str, source_url: str):
    provider_choice = (provider_choice or "").strip().lower()
    url = (source_url or "").strip()

    if provider_choice in ("", "auto"):
        provider, embed_url = normalize_embed(url)
        embed_html = ""
        if provider == "reddit":
            embed_html = reddit_oembed_html(url) or ""
            if not embed_html:
                provider = "custom"
        if provider == "tiktok":
            embed_html = tiktok_oembed_html(url) or ""
            if not embed_html:
                provider = "custom"
        return provider, embed_url, embed_html

    if provider_choice == "reddit":
        html = reddit_oembed_html(url) or ""
        return ("reddit", url, html) if html else ("custom", url, "")

    if provider_choice == "tiktok":
        html = tiktok_oembed_html(url) or ""
        return ("tiktok", url, html) if html else ("custom", url, "")

    if provider_choice == "youtube":
        p, e = normalize_embed(url)
        return ("youtube", e, "") if p == "youtube" else ("youtube", url, "")

    if provider_choice == "vimeo":
        p, e = normalize_embed(url)
        return ("vimeo", e, "") if p == "vimeo" else ("vimeo", url, "")

    if provider_choice == "loom":
        p, e = normalize_embed(url)
        return ("loom", e, "") if p == "loom" else ("loom", url, "")

    return ("custom", url, "")


# ---------- Playlist helpers ----------
def get_video_playlist(db, video_id: int):
    row = db.execute(
        q(
            """
            SELECT p.id as playlist_id, p.name as playlist_name
            FROM playlist_items pi
            JOIN playlists p ON p.id = pi.playlist_id
            WHERE pi.video_id = ?
            LIMIT 1
            """,
            """
            SELECT p.id as playlist_id, p.name as playlist_name
            FROM playlist_items pi
            JOIN playlists p ON p.id = pi.playlist_id
            WHERE pi.video_id = %s
            LIMIT 1
            """,
        ),
        (video_id,),
    ).fetchone()
    return row


def get_playlist_items(db, playlist_id: int):
    return db.execute(
        q(
            f"""
            SELECT v.*, pi.position
            FROM playlist_items pi
            JOIN videos v ON v.id = pi.video_id
            WHERE pi.playlist_id = ?
            ORDER BY pi.position ASC, {dt("v.created_at")} DESC
            """,
            f"""
            SELECT v.*, pi.position
            FROM playlist_items pi
            JOIN videos v ON v.id = pi.video_id
            WHERE pi.playlist_id = %s
            ORDER BY pi.position ASC, {dt("v.created_at")} DESC
            """,
        ),
        (playlist_id,),
    ).fetchall()


def get_next_in_playlist_id(db, playlist_id: int, current_video_id: int):
    cur = db.execute(
        q(
            "SELECT position FROM playlist_items WHERE playlist_id=? AND video_id=?",
            "SELECT position FROM playlist_items WHERE playlist_id=%s AND video_id=%s",
        ),
        (playlist_id, current_video_id),
    ).fetchone()
    if not cur:
        return None
    current_pos = int(cur["position"])

    nxt = db.execute(
        q(
            """
            SELECT video_id FROM playlist_items
            WHERE playlist_id=? AND position > ?
            ORDER BY position ASC
            LIMIT 1
            """,
            """
            SELECT video_id FROM playlist_items
            WHERE playlist_id=%s AND position > %s
            ORDER BY position ASC
            LIMIT 1
            """,
        ),
        (playlist_id, current_pos),
    ).fetchone()
    return int(nxt["video_id"]) if nxt else None


# ---------- Routes ----------
@app.route("/")
def index():
    db = get_db()

    qtext = (request.args.get("q") or "").strip()
    category = (request.args.get("cat") or "").strip()
    sort = (request.args.get("sort") or "new").strip().lower()
    if sort not in ("new", "views", "likes"):
        sort = "new"

    categories = db.execute(
        f"""
        SELECT DISTINCT TRIM(category) AS c
        FROM videos
        WHERE TRIM(category) != ''
        ORDER BY LOWER(TRIM(category)) ASC
        """
    ).fetchall()
    categories = [r["c"] for r in categories if r["c"]]

    where = []
    params = []

    if qtext:
        op = like_op()
        where.append(f"(title {op} %s OR description {op} %s OR category {op} %s)" if IS_PG
                     else f"(title {op} ? OR description {op} ? OR category {op} ?)")
        params += [f"%{qtext}%", f"%{qtext}%", f"%{qtext}%"]

    if category:
        where.append("TRIM(category) = %s" if IS_PG else "TRIM(category) = ?")
        params.append(category)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    if sort == "views":
        order_sql = f"ORDER BY views DESC, {dt('created_at')} DESC"
    elif sort == "likes":
        order_sql = f"ORDER BY likes DESC, {dt('created_at')} DESC"
    else:
        order_sql = f"ORDER BY {dt('created_at')} DESC"

    rows = db.execute(
        f"SELECT * FROM videos {where_sql} {order_sql}",
        tuple(params),
    ).fetchall()

    return render_template(
        "index.html",
        videos=rows,
        q=qtext,
        categories=categories,
        selected_cat=category,
        sort=sort,
    )


@app.route("/watch/<int:video_id>")
def watch(video_id: int):
    db = get_db()
    video = db.execute(
        q("SELECT * FROM videos WHERE id=?", "SELECT * FROM videos WHERE id=%s"),
        (video_id,),
    ).fetchone()
    if not video:
        abort(404)

    noview = (request.args.get("noview") or "") == "1"
    if not noview:
        db.execute(
            q("UPDATE videos SET views = views + 1 WHERE id=?", "UPDATE videos SET views = views + 1 WHERE id=%s"),
            (video_id,),
        )
        db.commit()

    user = current_user()
    if user:
        now = datetime.utcnow().isoformat()
        db.execute(
            q(
                """
                INSERT INTO watch_history (user_id, video_id, last_watched_at, watch_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, video_id)
                DO UPDATE SET last_watched_at = excluded.last_watched_at,
                             watch_count = watch_count + 1
                """,
                """
                INSERT INTO watch_history (user_id, video_id, last_watched_at, watch_count)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT(user_id, video_id)
                DO UPDATE SET last_watched_at = EXCLUDED.last_watched_at,
                             watch_count = watch_history.watch_count + 1
                """,
            ),
            (user["id"], video_id, now),
        )
        db.commit()

    video = db.execute(
        q("SELECT * FROM videos WHERE id=?", "SELECT * FROM videos WHERE id=%s"),
        (video_id,),
    ).fetchone()

    comments = db.execute(
        q(
            f"SELECT * FROM comments WHERE video_id=? ORDER BY {dt('created_at')} DESC",
            f"SELECT * FROM comments WHERE video_id=%s ORDER BY {dt('created_at')} DESC",
        ),
        (video_id,),
    ).fetchall()

    liked = False
    if user:
        liked = db.execute(
            q(
                "SELECT 1 FROM video_likes WHERE user_id=? AND video_id=?",
                "SELECT 1 FROM video_likes WHERE user_id=%s AND video_id=%s",
            ),
            (user["id"], video_id),
        ).fetchone() is not None

    playlist = get_video_playlist(db, video_id)
    playlist_items = []
    next_in_playlist_id = None

    if playlist:
        pid = int(playlist["playlist_id"])
        playlist_items = get_playlist_items(db, pid)
        next_in_playlist_id = get_next_in_playlist_id(db, pid, video_id)

    recommended = []
    if not playlist:
        recommended = db.execute(
            q(
                f"""
                SELECT * FROM videos
                WHERE id != ?
                ORDER BY (provider = ?) DESC, {dt('created_at')} DESC
                LIMIT 12
                """,
                f"""
                SELECT * FROM videos
                WHERE id != %s
                ORDER BY (provider = %s) DESC, {dt('created_at')} DESC
                LIMIT 12
                """,
            ),
            (video_id, video["provider"]),
        ).fetchall()

    return render_template(
        "watch.html",
        video=video,
        comments=comments,
        recommended=recommended,
        playlist=playlist,
        playlist_items=playlist_items,
        next_in_playlist_id=next_in_playlist_id,
        liked=liked,
    )


@app.route("/watch/<int:video_id>/like", methods=["POST"])
def like(video_id: int):
    db = get_db()
    v = db.execute(
        q("SELECT id FROM videos WHERE id=?", "SELECT id FROM videos WHERE id=%s"),
        (video_id,),
    ).fetchone()
    if not v:
        abort(404)

    user = current_user()
    if not user:
        wants_json = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or "")
            or (request.args.get("ajax") == "1")
        )
        if wants_json:
            return jsonify({"ok": False, "error": "login_required"}), 401
        flash(t("like_requires_login"), "error")
        return redirect(url_for("watch", video_id=video_id, noview=1))

    try:
        db.execute(
            q(
                "INSERT INTO video_likes (user_id, video_id, created_at) VALUES (?, ?, ?)",
                "INSERT INTO video_likes (user_id, video_id, created_at) VALUES (%s, %s, %s)",
            ),
            (user["id"], video_id, datetime.utcnow().isoformat()),
        )
        db.execute(
            q("UPDATE videos SET likes = likes + 1 WHERE id=?", "UPDATE videos SET likes = likes + 1 WHERE id=%s"),
            (video_id,),
        )
        db.commit()
        liked_now = True
    except Exception as e:
        if is_unique_violation(e):
            liked_now = True
        else:
            db.rollback() if IS_PG else None
            flash(t("like_failed"), "error")
            return redirect(url_for("watch", video_id=video_id, noview=1))

    likes_row = db.execute(
        q("SELECT likes FROM videos WHERE id=?", "SELECT likes FROM videos WHERE id=%s"),
        (video_id,),
    ).fetchone()
    likes = int(likes_row["likes"]) if likes_row else 0

    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
        or (request.args.get("ajax") == "1")
    )
    if wants_json:
        return jsonify({"ok": True, "video_id": video_id, "likes": likes, "liked": liked_now})

    return redirect(url_for("watch", video_id=video_id, noview=1))


@app.route("/watch/<int:video_id>/comment", methods=["POST"])
def comment(video_id: int):
    db = get_db()
    v = db.execute(
        q("SELECT id FROM videos WHERE id=?", "SELECT id FROM videos WHERE id=%s"),
        (video_id,),
    ).fetchone()
    if not v:
        abort(404)

    user = current_user()
    author = (request.form.get("author") or "").strip()
    body = (request.form.get("body") or "").strip()

    if not body:
        flash(t("comment_empty"), "error")
        return redirect(url_for("watch", video_id=video_id, noview=1))

    if user and not author:
        author = user["username"]
    if not author:
        author = t("anon")

    db.execute(
        q(
            """
            INSERT INTO comments (video_id, user_id, author, body, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            """
            INSERT INTO comments (video_id, user_id, author, body, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
        ),
        (video_id, user["id"] if user else None, author[:50], body[:1000], datetime.utcnow().isoformat()),
    )
    db.commit()
    flash(t("comment_posted"), "ok")
    return redirect(url_for("watch", video_id=video_id, noview=1))


@app.route("/history")
def history():
    if not session.get("user_id"):
        return require_login()

    user = current_user()
    db = get_db()
    rows = db.execute(
        q(
            f"""
            SELECT h.last_watched_at, h.watch_count, v.*
            FROM watch_history h
            JOIN videos v ON v.id = h.video_id
            WHERE h.user_id = ?
            ORDER BY {dt('h.last_watched_at')} DESC
            """,
            f"""
            SELECT h.last_watched_at, h.watch_count, v.*
            FROM watch_history h
            JOIN videos v ON v.id = h.video_id
            WHERE h.user_id = %s
            ORDER BY {dt('h.last_watched_at')} DESC
            """,
        ),
        (user["id"],),
    ).fetchall()

    return render_template("history.html", rows=rows)


# ---------- Auth ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    nxt = request.args.get("next") or url_for("index")
    if request.method == "POST":
        nxt = request.form.get("next") or url_for("index")
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        db = get_db()
        user = db.execute(
            q(
                "SELECT id, username, password_hash, is_admin FROM users WHERE username=?",
                "SELECT id, username, password_hash, is_admin FROM users WHERE username=%s",
            ),
            (username,),
        ).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            flash(t("bad_login"), "error")
            return render_template("login.html", next=nxt)

        session["user_id"] = user["id"]
        flash(t("logged_in_as", username=user["username"]), "ok")
        return redirect(nxt)

    return render_template("login.html", next=nxt)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash(t("logged_out"), "ok")
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "")
        password2 = (request.form.get("password2") or "")

        if not username or not password:
            flash(t("register_required"), "error")
            return render_template("register.html")

        if password != password2:
            flash(t("passwords_no_match"), "error")
            return render_template("register.html")

        if username.lower() == ADMIN_USERNAME.lower():
            flash(t("username_reserved"), "error")
            return render_template("register.html")

        db = get_db()
        try:
            db.execute(
                q(
                    "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, 0, ?)",
                    "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (%s, %s, 0, %s)",
                ),
                (username, generate_password_hash(password), datetime.utcnow().isoformat()),
            )
            db.commit()
        except Exception as e:
            if is_unique_violation(e):
                flash(t("username_exists"), "error")
                return render_template("register.html")
            raise

        flash(t("account_created"), "ok")
        return redirect(url_for("login"))

    return render_template("register.html")


# ---------- Admin ----------
@app.route("/admin")
def admin():
    require_admin()
    db = get_db()
    videos = db.execute(
        f"SELECT * FROM videos ORDER BY {dt('created_at')} DESC"
    ).fetchall()
    return render_template("admin.html", videos=videos)


@app.route("/admin/add", methods=["GET", "POST"])
def admin_add():
    require_admin()
    db = get_db()

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        source_url = (request.form.get("source_url") or "").strip()
        thumbnail_url = (request.form.get("thumbnail_url") or "").strip()
        provider_choice = (request.form.get("provider") or "auto").strip().lower()
        category = (request.form.get("category") or "").strip()

        if not title or not source_url:
            flash(t("admin_need_title_url"), "error")
            return render_template("admin_add.html")

        provider, embed_url, embed_html = force_provider_embed(provider_choice, source_url)

        db.execute(
            q(
                """
                INSERT INTO videos
                  (title, description, source_url, embed_url, thumbnail_url, provider, created_at, embed_html, category)
                VALUES
                  (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                """
                INSERT INTO videos
                  (title, description, source_url, embed_url, thumbnail_url, provider, created_at, embed_html, category)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
            ),
            (title, description, source_url, embed_url, thumbnail_url, provider,
             datetime.utcnow().isoformat(), embed_html, category),
        )
        db.commit()
        flash(t("video_added"), "ok")
        return redirect(url_for("admin"))

    return render_template("admin_add.html")


@app.route("/admin/video/<int:video_id>/edit", methods=["GET", "POST"])
def admin_video_edit(video_id: int):
    require_admin()
    db = get_db()
    video = db.execute(
        q("SELECT * FROM videos WHERE id=?", "SELECT * FROM videos WHERE id=%s"),
        (video_id,),
    ).fetchone()
    if not video:
        abort(404)

    playlists = db.execute(f"SELECT id, name FROM playlists ORDER BY {dt('created_at')} DESC").fetchall()
    current_pl = get_video_playlist(db, video_id)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        source_url = (request.form.get("source_url") or "").strip()
        thumbnail_url = (request.form.get("thumbnail_url") or "").strip()
        provider_choice = (request.form.get("provider") or "auto").strip().lower()
        category = (request.form.get("category") or "").strip()

        playlist_id = (request.form.get("playlist_id") or "").strip()
        new_playlist_name = (request.form.get("new_playlist_name") or "").strip()
        position_str = (request.form.get("playlist_position") or "").strip()
        try:
            position = int(position_str) if position_str else 1
            if position < 1:
                position = 1
        except Exception:
            position = 1

        if not title or not source_url:
            flash(t("admin_need_title_url"), "error")
            return redirect(url_for("admin_video_edit", video_id=video_id))

        provider, embed_url, embed_html = force_provider_embed(provider_choice, source_url)

        db.execute(
            q(
                """
                UPDATE videos
                SET title=?, description=?, source_url=?, embed_url=?, thumbnail_url=?,
                    provider=?, embed_html=?, category=?
                WHERE id=?
                """,
                """
                UPDATE videos
                SET title=%s, description=%s, source_url=%s, embed_url=%s, thumbnail_url=%s,
                    provider=%s, embed_html=%s, category=%s
                WHERE id=%s
                """,
            ),
            (title, description, source_url, embed_url, thumbnail_url, provider, embed_html, category, video_id),
        )

        chosen_playlist_id = None
        if new_playlist_name:
            if IS_PG:
                chosen_playlist_id = db.execute(
                    "INSERT INTO playlists (name, created_at) VALUES (%s, %s) RETURNING id",
                    (new_playlist_name[:120], datetime.utcnow().isoformat()),
                ).fetchone()["id"]
            else:
                db.execute(
                    "INSERT INTO playlists (name, created_at) VALUES (?, ?)",
                    (new_playlist_name[:120], datetime.utcnow().isoformat()),
                )
                chosen_playlist_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        elif playlist_id and playlist_id != "none":
            try:
                chosen_playlist_id = int(playlist_id)
            except Exception:
                chosen_playlist_id = None

        if current_pl:
            old_id = int(current_pl["playlist_id"])
            if (chosen_playlist_id is None) or (chosen_playlist_id != old_id):
                db.execute(
                    q(
                        "DELETE FROM playlist_items WHERE playlist_id=? AND video_id=?",
                        "DELETE FROM playlist_items WHERE playlist_id=%s AND video_id=%s",
                    ),
                    (old_id, video_id),
                )

        if chosen_playlist_id is not None:
            db.execute(
                q(
                    """
                    INSERT INTO playlist_items (playlist_id, video_id, position)
                    VALUES (?, ?, ?)
                    ON CONFLICT(playlist_id, video_id)
                    DO UPDATE SET position=excluded.position
                    """,
                    """
                    INSERT INTO playlist_items (playlist_id, video_id, position)
                    VALUES (%s, %s, %s)
                    ON CONFLICT(playlist_id, video_id)
                    DO UPDATE SET position=EXCLUDED.position
                    """,
                ),
                (chosen_playlist_id, video_id, position),
            )

        db.commit()
        flash(t("video_updated"), "ok")
        return redirect(url_for("admin"))

    return render_template(
        "admin_video_edit.html",
        video=video,
        playlists=playlists,
        current_playlist=current_pl,
    )


@app.route("/admin/delete/<int:video_id>", methods=["POST"])
def admin_delete(video_id: int):
    require_admin()
    db = get_db()
    db.execute(
        q("DELETE FROM videos WHERE id=?", "DELETE FROM videos WHERE id=%s"),
        (video_id,),
    )
    db.commit()
    flash(t("video_deleted"), "ok")
    return redirect(url_for("admin"))


# ---------- Admin: Users ----------
@app.route("/admin/users")
def admin_users():
    require_admin()
    db = get_db()
    users = db.execute(
        f"SELECT id, username, is_admin, created_at FROM users ORDER BY {dt('created_at')} DESC"
    ).fetchall()
    return render_template("admin_users.html", users=users, main_admin=ADMIN_USERNAME)


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
def admin_user_edit(user_id: int):
    require_admin()
    db = get_db()
    user = db.execute(
        q(
            "SELECT id, username, is_admin, created_at FROM users WHERE id=?",
            "SELECT id, username, is_admin, created_at FROM users WHERE id=%s",
        ),
        (user_id,),
    ).fetchone()
    if not user:
        abort(404)

    is_main_admin = (user["username"] or "").lower() == ADMIN_USERNAME.lower()
    if request.method == "POST" and is_main_admin:
        flash(t("cannot_edit_main_admin"), "error")
        return redirect(url_for("admin_users"))

    if request.method == "POST":
        new_username = (request.form.get("username") or "").strip()
        new_password = (request.form.get("password") or "").strip()
        is_admin = 1 if (request.form.get("is_admin") == "on") else 0

        if new_username and new_username != user["username"]:
            try:
                db.execute(
                    q("UPDATE users SET username=? WHERE id=?", "UPDATE users SET username=%s WHERE id=%s"),
                    (new_username, user_id),
                )
                db.commit()
            except Exception as e:
                if is_unique_violation(e):
                    flash(t("username_exists"), "error")
                    return redirect(url_for("admin_user_edit", user_id=user_id))
                raise

        db.execute(
            q("UPDATE users SET is_admin=? WHERE id=?", "UPDATE users SET is_admin=%s WHERE id=%s"),
            (is_admin, user_id),
        )

        if new_password:
            db.execute(
                q(
                    "UPDATE users SET password_hash=? WHERE id=?",
                    "UPDATE users SET password_hash=%s WHERE id=%s",
                ),
                (generate_password_hash(new_password), user_id),
            )

        db.commit()
        flash(t("user_updated"), "ok")
        return redirect(url_for("admin_users"))

    return render_template("admin_user_edit.html", u=user, is_main_admin=is_main_admin)


if __name__ == "__main__":
    # Lokal dev. Render/Gunicorn använder inte detta.
    app.run(debug=True, host="127.0.0.1", port=5000)
