"""Accounts: captcha, register / login (password or Google), session cookie, profile & settings."""
import re
from datetime import datetime, timedelta

import httpx
from bson import ObjectId
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from . import progress, security
from .config import settings
from .db import enabled, get_db
from .errors import ApiError

router = APIRouter(prefix="/api")
COOKIE = "avtv_session"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
PASSWORD_RE = re.compile(r"^[\x21-\x7E]{8,64}$")  # letters, digits and special characters, no spaces
RESERVED = {"admin", "administrator", "root", "support", "moderator", "mod", "staff", "system", "anivoid", "anivoidtv", "null", "undefined"}
LINK_RE = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|net|org|io|me|tv|to|cz|xyz|gg|ly|cc|co|info|site|app)\b)", re.I)
STATUSES = ["watching", "completed", "on_hold", "dropped", "plan_to_watch"]


# ------------------------------------------------------------------ helpers
def client_ip(request: Request) -> str:
    if settings.proxy_secret and request.headers.get("x-proxy-secret") == settings.proxy_secret:
        return request.headers.get("x-client-ip", "")[:64] or "unknown"
    return request.client.host if request.client else "unknown"


def throttle(request: Request, action: str, limit: int, window: float, extra: str = "") -> None:
    if not security.limiter.allow(f"{action}:{client_ip(request)}:{extra}", limit, window):
        raise ApiError(429, "Too many attempts. Please wait a bit and try again.")


def oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:  # noqa: BLE001
        raise ApiError(404, "Not found")


def current_user(request: Request) -> dict | None:
    if not enabled():
        return None
    body = security.unsign(request.cookies.get(COOKIE), "s")
    if not body:
        return None
    u = get_db().users.find_one({"_id": oid(body["u"])})
    if not u or u.get("pw_ver", 0) != body.get("pv", 0):
        return None
    return u


def require_user(request: Request) -> dict:
    u = current_user(request)
    if not u:
        raise ApiError(401, "Please sign in first.", auth_required=True)
    return u


def set_session(response: Response, user: dict) -> None:
    ttl = settings.session_days * 86400
    token = security.sign({"t": "s", "u": str(user["_id"]), "pv": user.get("pw_ver", 0)}, ttl)
    response.set_cookie(COOKIE, token, max_age=ttl, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


def iso(d) -> str | None:
    return d.isoformat() if isinstance(d, datetime) else None


def list_counts(db, uid) -> dict:
    counts = {s: 0 for s in STATUSES}
    for row in db.anime_list.aggregate([{"$match": {"user_id": uid}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        counts[row["_id"]] = row["n"]
    return counts


def stats_of(db, u: dict) -> dict:
    counts = list_counts(db, u["_id"])
    st = u.get("stats", {})
    vp = u.get("vp", 0)
    joined = u.get("created_at")
    days = max(0, (progress.now() - joined).days) if isinstance(joined, datetime) else 0
    return {
        "episodes": st.get("episodes", 0), "minutes": st.get("minutes", 0),
        "hours": round(st.get("minutes", 0) / 60, 1), "comments": st.get("comments", 0),
        "list_counts": counts, "list_total": sum(counts.values()), "completed": counts["completed"],
        "best_streak": u.get("best_streak", 0), "days_on_site": days, "rank": progress.rank_index(vp),
    }


def avatar_of(u: dict) -> dict:
    a = u.get("avatar") or {}
    default_bg = sum(map(ord, u["username_lower"])) % progress.AVATAR_BG_COUNT  # stable across restarts
    return {"bg": a.get("bg", default_bg), "icon": a.get("icon", "initial"), "frame": a.get("frame", "none")}


def brief(u: dict) -> dict:
    """Tiny public card used inside comments, lists, friends."""
    return {"username": u["username"], "avatar": avatar_of(u), "rank": progress.rank_info(u.get("vp", 0))["title"]}


def public_view(db, u: dict, me: bool = False) -> dict:
    stats = stats_of(db, u)
    vp = u.get("vp", 0)
    out = {
        "username": u["username"], "avatar": avatar_of(u), "bio": u.get("bio", ""),
        "joined": iso(u.get("created_at")), "vp": vp, "rank": progress.rank_info(vp),
        "stats": stats, "favorites": u.get("favorites", []), "badges": progress.badges_for(stats),
        "streak": u.get("streak", 0), "privacy": u.get("privacy", {"show_list": True}),
    }
    if me:
        out.update({
            "id": str(u["_id"]), "email": u.get("email"), "has_password": bool(u.get("pw_hash")),
            "google_linked": bool(u.get("google_sub")), "checked_in_today": u.get("last_checkin") == progress.today(),
            "frames": progress.frames_for(vp), "avatar_icons": progress.AVATAR_ICONS,
            "avatar_bg_count": progress.AVATAR_BG_COUNT,
        })
    return out


def validate_username(name: str) -> str:
    name = (name or "").strip()
    if not USERNAME_RE.match(name):
        raise ApiError(400, "Username must be 3-20 characters: letters, numbers and underscore only.")
    if name.lower() in RESERVED:
        raise ApiError(400, "That username is reserved.")
    return name


def validate_password(pw: str, username: str = "") -> str:
    if not PASSWORD_RE.match(pw or ""):
        raise ApiError(400, "Password must be 8-64 characters (letters, numbers, symbols; no spaces).")
    if username and pw.lower() == username.lower():
        raise ApiError(400, "Password can't be the same as your username.")
    return pw


def create_user(db, username: str, *, pw_hash: str | None = None, email: str | None = None, google_sub: str | None = None) -> dict:
    now = progress.now()
    doc = {
        "username": username, "username_lower": username.lower(), "pw_hash": pw_hash, "pw_ver": 0,
        "email": email, "email_lower": email.lower() if email else None, "google_sub": google_sub,
        "created_at": now, "bio": "", "favorites": [], "avatar": {}, "privacy": {"show_list": True},
        "vp": 0, "stats": {"episodes": 0, "minutes": 0, "comments": 0}, "streak": 0, "best_streak": 0,
    }
    for k in ("email", "email_lower", "google_sub"):
        if doc[k] is None:
            del doc[k]  # keep partial unique indexes clean
    try:
        doc["_id"] = db.users.insert_one(doc).inserted_id
    except DuplicateKeyError:
        raise ApiError(409, "That username is already taken.")
    progress.award(db, doc, "welcome")
    return doc


# ------------------------------------------------------------------ models
class CaptchaIn(BaseModel):
    captcha_token: str = ""
    captcha_answer: str = ""


class RegisterIn(CaptchaIn):
    username: str
    password: str
    confirm: str | None = None


class LoginIn(CaptchaIn):
    username: str
    password: str


class GoogleIn(BaseModel):
    credential: str


class GoogleCompleteIn(BaseModel):
    ticket: str
    username: str


class ProfileIn(BaseModel):
    bio: str | None = Field(default=None, max_length=400)
    avatar: dict | None = None
    favorites: list[dict] | None = None
    privacy: dict | None = None


class PasswordIn(BaseModel):
    current: str = ""
    new: str


class UsernameIn(BaseModel):
    username: str
    password: str = ""


# ------------------------------------------------------------------ public config + captcha
@router.get("/config")
def config():
    return {"success": True, "results": {"accounts": enabled(), "google_client_id": settings.google_client_id or None}}


@router.get("/auth/captcha")
def captcha(request: Request):
    throttle(request, "captcha", 40, 600)
    return {"success": True, "results": security.new_captcha()}


# ------------------------------------------------------------------ register / login
@router.post("/auth/register")
def register(body: RegisterIn, request: Request, response: Response):
    db = get_db()
    throttle(request, "register", 8, 3600)
    if not security.check_captcha(db, body.captcha_token, body.captcha_answer):
        raise ApiError(400, "Captcha is wrong or expired. Try the new one.", captcha_failed=True)
    username = validate_username(body.username)
    validate_password(body.password, username)
    if body.confirm is not None and body.confirm != body.password:
        raise ApiError(400, "Passwords don't match.")
    if db.users.find_one({"username_lower": username.lower()}):
        raise ApiError(409, "That username is already taken.")
    user = create_user(db, username, pw_hash=security.hash_password(body.password))
    set_session(response, user)
    return {"success": True, "results": public_view(db, user, me=True)}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    db = get_db()
    throttle(request, "login", 15, 600)
    if not security.check_captcha(db, body.captcha_token, body.captcha_answer):
        raise ApiError(400, "Captcha is wrong or expired. Try the new one.", captcha_failed=True)
    ident = body.username.strip().lower()
    user = db.users.find_one({"username_lower": ident}) or db.users.find_one({"email_lower": ident})
    if not user or not security.verify_password(body.password, user.get("pw_hash")):
        security.limiter.allow(f"badlogin:{ident}", 10**6, 900)  # keeps a trace for future per-user lockouts
        raise ApiError(401, "Wrong username or password." if not (user and not user.get("pw_hash"))
                       else "This account uses Google sign-in. Use the Google button.")
    set_session(response, user)
    return {"success": True, "results": public_view(db, user, me=True)}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"success": True}


# ------------------------------------------------------------------ Google
def _verify_google(credential: str) -> dict:
    if not settings.google_client_id:
        raise ApiError(503, "Google sign-in is not configured.")
    try:
        r = httpx.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": credential}, timeout=10)
    except httpx.HTTPError:
        raise ApiError(502, "Could not reach Google. Try again.")
    info = r.json() if r.status_code == 200 else {}
    if info.get("aud") != settings.google_client_id or str(info.get("email_verified")).lower() != "true" or not info.get("sub"):
        raise ApiError(401, "Google sign-in failed.")
    return info


@router.post("/auth/google")
def google_login(body: GoogleIn, request: Request, response: Response):
    db = get_db()
    throttle(request, "google", 20, 600)
    info = _verify_google(body.credential)
    sub, email = info["sub"], info["email"]
    user = db.users.find_one({"google_sub": sub}) or db.users.find_one({"email_lower": email.lower()})
    if user:  # existing account (same Google or same verified email): sign in and link
        if not user.get("google_sub"):
            db.users.update_one({"_id": user["_id"]}, {"$set": {"google_sub": sub}})
        set_session(response, user)
        return {"success": True, "results": {"status": "ok", "user": public_view(db, user, me=True)}}
    ticket = security.sign({"t": "g", "sub": sub, "email": email}, 600)
    return {"success": True, "results": {"status": "need_username", "ticket": ticket, "email": email}}


@router.post("/auth/google/complete")
def google_complete(body: GoogleCompleteIn, request: Request, response: Response):
    db = get_db()
    throttle(request, "google", 20, 600)
    t = security.unsign(body.ticket, "g")
    if not t:
        raise ApiError(400, "Sign-in session expired. Please try Google again.")
    username = validate_username(body.username)
    if db.users.find_one({"username_lower": username.lower()}):
        raise ApiError(409, "That username is already taken.")
    user = create_user(db, username, email=t["email"], google_sub=t["sub"])
    set_session(response, user)
    return {"success": True, "results": public_view(db, user, me=True)}


# ------------------------------------------------------------------ me
@router.get("/me")
def me(request: Request):
    u = require_user(request)
    return {"success": True, "results": public_view(get_db(), u, me=True)}


def _clean_favorites(items: list[dict]) -> list[dict]:
    out, seen = [], set()
    for it in items[:10]:
        try:
            aid = int(it.get("id"))
        except (TypeError, ValueError):
            continue
        if aid in seen or aid <= 0:
            continue
        seen.add(aid)
        out.append({"id": aid, "title": str(it.get("title", ""))[:160], "poster": str(it.get("poster", ""))[:400]})
    return out


@router.patch("/me")
def update_me(body: ProfileIn, request: Request):
    db, u = get_db(), require_user(request)
    sets: dict = {}
    if body.bio is not None:
        bio = re.sub(r"\n{3,}", "\n\n", body.bio.strip())
        if LINK_RE.search(bio):
            raise ApiError(400, "Bio is plain text only: no links or websites.")
        sets["bio"] = bio
    if body.avatar is not None:
        a, cur = body.avatar, avatar_of(u)
        bg = a.get("bg", cur["bg"])
        icon = a.get("icon", cur["icon"])
        frame = a.get("frame", cur["frame"])
        if not isinstance(bg, int) or not 0 <= bg < progress.AVATAR_BG_COUNT:
            raise ApiError(400, "Invalid avatar colour.")
        if icon not in progress.AVATAR_ICONS:
            raise ApiError(400, "Invalid avatar icon.")
        if frame not in progress.FRAMES:
            raise ApiError(400, "Invalid avatar frame.")
        if progress.rank_index(u.get("vp", 0)) < progress.FRAMES[frame]:
            raise ApiError(403, f"That frame unlocks at rank {progress.RANKS[progress.FRAMES[frame]][1]}.")
        sets["avatar"] = {"bg": bg, "icon": icon, "frame": frame}
    if body.favorites is not None:
        sets["favorites"] = _clean_favorites(body.favorites)
    if body.privacy is not None:
        sets["privacy"] = {"show_list": bool(body.privacy.get("show_list", True))}
    if sets:
        db.users.update_one({"_id": u["_id"]}, {"$set": sets})
        u.update(sets)
    return {"success": True, "results": public_view(db, u, me=True)}


@router.post("/me/password")
def change_password(body: PasswordIn, request: Request, response: Response):
    db, u = get_db(), require_user(request)
    throttle(request, "pwchange", 8, 3600, str(u["_id"]))
    if u.get("pw_hash") and not security.verify_password(body.current, u["pw_hash"]):
        raise ApiError(400, "Current password is wrong.")
    validate_password(body.new, u["username"])
    db.users.update_one({"_id": u["_id"]}, {"$set": {"pw_hash": security.hash_password(body.new)}, "$inc": {"pw_ver": 1}})
    u = db.users.find_one({"_id": u["_id"]})
    set_session(response, u)  # other devices are signed out (pw_ver changed)
    return {"success": True, "message": "Password updated. Other devices were signed out."}


@router.post("/me/username")
def change_username(body: UsernameIn, request: Request):
    db, u = get_db(), require_user(request)
    name = validate_username(body.username)
    if u.get("pw_hash") and not security.verify_password(body.password, u["pw_hash"]):
        raise ApiError(400, "Password is wrong.")
    last = u.get("username_changed_at")
    if isinstance(last, datetime) and progress.now() - last < timedelta(days=30):
        raise ApiError(429, "You can change your username once every 30 days.")
    if name.lower() != u["username_lower"] and db.users.find_one({"username_lower": name.lower()}):
        raise ApiError(409, "That username is already taken.")
    try:
        db.users.update_one({"_id": u["_id"]}, {"$set": {"username": name, "username_lower": name.lower(),
                                                       "username_changed_at": progress.now()}})
    except DuplicateKeyError:
        raise ApiError(409, "That username is already taken.")
    u = db.users.find_one({"_id": u["_id"]})
    return {"success": True, "results": public_view(db, u, me=True)}


@router.post("/me/checkin")
def daily_checkin(request: Request):
    db, u = get_db(), require_user(request)
    res = progress.checkin(db, u)
    u = db.users.find_one({"_id": u["_id"]})
    return {"success": True, "results": {**res, "rank": progress.rank_info(u.get("vp", 0))}}


@router.get("/me/vp")
def vp_history(request: Request):
    db, u = get_db(), require_user(request)
    rows = db.vp_log.find({"user_id": u["_id"]}).sort("at", -1).limit(50)
    return {"success": True, "results": [{"delta": r["delta"], "reason": r["reason"], "at": iso(r["at"])} for r in rows]}
