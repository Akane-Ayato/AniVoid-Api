"""Reports from members + minimal moderation tools (protected by ADMIN_TOKEN, not by cookies)."""
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from . import progress, security
from .accounts import oid, require_user, throttle
from .config import settings
from .db import get_db
from .errors import ApiError
from .media import drop_main

router = APIRouter(prefix="/api")


class ReportIn(BaseModel):
    type: str = Field(pattern="^(comment|media|user)$")
    target: str = Field(max_length=60)
    reason: str = Field(default="", max_length=300)


def _admin(token: str) -> None:
    if not settings.admin_token or not security.safe_equal(token, settings.admin_token):
        raise ApiError(401, "Invalid admin token")


@router.post("/report")
def report(body: ReportIn, request: Request):
    db, u = get_db(), require_user(request)
    throttle(request, "report", 10, 3600, str(u["_id"]))
    db.reports.insert_one({"type": body.type, "target": body.target, "reason": body.reason.strip(), "by": u["_id"], "created": progress.now(), "open": True})
    return {"success": True, "message": "Thanks, a moderator will take a look."}


@router.get("/admin/reports")
def admin_reports(x_admin_token: str = Header(default="")):
    _admin(x_admin_token)
    rows = get_db().reports.find({"open": True}).sort("created", -1).limit(100)
    return {"success": True, "results": [{"id": str(r["_id"]), "type": r["type"], "target": r["target"], "reason": r["reason"],
                                          "created": r["created"].isoformat()} for r in rows]}


@router.delete("/admin/comments/{comment_id}")
def admin_delete_comment(comment_id: str, x_admin_token: str = Header(default="")):
    _admin(x_admin_token)
    db = get_db()
    c = db.comments.find_one({"_id": oid(comment_id)})
    if not c:
        raise ApiError(404, "Comment not found.")
    n = 1 + (db.comments.delete_many({"parent_id": c["_id"]}).deleted_count if not c.get("parent_id") else 0)
    db.comments.delete_one({"_id": c["_id"]})
    db.reports.update_many({"type": "comment", "target": comment_id}, {"$set": {"open": False}})
    return {"success": True, "results": {"removed": n}}


@router.delete("/admin/media/{media_id}")
def admin_delete_media(media_id: str, x_admin_token: str = Header(default="")):
    _admin(x_admin_token)
    db = get_db()
    m = db.media.find_one({"_id": oid(media_id)}, {"data": 0})
    if not m:
        raise ApiError(404, "Picture not found.")
    db.media.delete_one({"_id": m["_id"]})
    drop_main(db, None, m)
    db.reports.update_many({"type": "media", "target": media_id}, {"$set": {"open": False}})
    return {"success": True}


@router.post("/admin/users/{username}/ban")
def admin_ban(username: str, unban: bool = False, x_admin_token: str = Header(default="")):
    _admin(x_admin_token)
    db = get_db()
    u = db.users.find_one({"username_lower": username.lower()})
    if not u:
        raise ApiError(404, "User not found.")
    db.users.update_one({"_id": u["_id"]}, {"$set": {"banned": not unban}})
    if not unban:
        db.sessions.delete_many({"user_id": u["_id"]})
    return {"success": True, "results": {"username": u["username"], "banned": not unban}}
