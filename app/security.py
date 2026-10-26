"""Passwords, signed tokens, captcha and a tiny in-memory rate limiter (stdlib only)."""
import base64
import hashlib
import hmac
import json
import logging
import random
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from .config import settings

log = logging.getLogger("security")

_SECRET = (settings.session_secret or "").encode()
if not _SECRET:
    _SECRET = secrets.token_bytes(32)
    log.warning("SESSION_SECRET is not set: using a random one, all sessions reset on restart")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ------------------------------------------------------------------ passwords (scrypt)
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)
    return f"scrypt${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, salt, dk = stored.split("$")
        calc = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=2 ** 14, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(calc, _unb64(dk))
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ signed tokens
def sign(payload: dict, ttl: int) -> str:
    body = dict(payload, exp=int(time.time()) + ttl)
    raw = _b64(json.dumps(body, separators=(",", ":")).encode())
    return f"{raw}.{_b64(hmac.new(_SECRET, raw.encode(), hashlib.sha256).digest())}"


def unsign(token: str | None, typ: str) -> dict | None:
    try:
        raw, sig = (token or "").split(".")
        if not hmac.compare_digest(_b64(hmac.new(_SECRET, raw.encode(), hashlib.sha256).digest()), sig):
            return None
        body = json.loads(_unb64(raw))
        if body.get("t") != typ or body.get("exp", 0) < time.time():
            return None
        return body
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ captcha (server-issued, stateless + single use)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion
CAPTCHA_TTL = 300


def _ans_hash(nonce: str, answer: str) -> str:
    return hashlib.sha256(f"{_SECRET.hex()}|{nonce}|{answer.strip().upper()}".encode()).hexdigest()


def _captcha_svg(text: str) -> str:
    r = random.Random()
    w, h = 170, 56
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2a2236"/>'
             '<stop offset="1" stop-color="#1b1624"/></linearGradient></defs>',
             f'<rect width="{w}" height="{h}" rx="8" fill="url(#g)"/>']
    for _ in range(7):
        c = r.choice(["#ff6fa5", "#e8a854", "#6fd6a0", "#3fa8e8", "#9a90a8"])
        parts.append(f'<path d="M{r.randint(0, w)} {r.randint(0, h)} Q{r.randint(0, w)} {r.randint(0, h)} {r.randint(0, w)} {r.randint(0, h)}" '
                     f'stroke="{c}" stroke-opacity=".55" stroke-width="{r.choice([1, 1.5, 2])}" fill="none"/>')
    for _ in range(40):
        parts.append(f'<circle cx="{r.randint(0, w)}" cy="{r.randint(0, h)}" r="{r.choice([0.8, 1.2, 1.6])}" fill="#ffffff" fill-opacity=".35"/>')
    step = (w - 30) / len(text)
    for i, ch in enumerate(text):
        x, y = 18 + i * step, r.randint(35, 42)
        c = r.choice(["#f1ece8", "#ffd1e3", "#ffe2b3", "#c9f2dc", "#bfe3fa"])
        parts.append(f'<text x="{x:.1f}" y="{y}" font-size="{r.randint(27, 33)}" font-family="Verdana,Arial,monospace" font-weight="700" '
                     f'fill="{c}" transform="rotate({r.randint(-22, 22)} {x:.1f} {y})">{ch}</text>')
    parts.append("</svg>")
    return "data:image/svg+xml;base64," + base64.b64encode("".join(parts).encode()).decode()


def new_captcha() -> dict:
    answer = "".join(secrets.choice(ALPHABET) for _ in range(5))
    nonce = secrets.token_hex(8)
    return {"token": sign({"t": "c", "n": nonce, "h": _ans_hash(nonce, answer)}, CAPTCHA_TTL), "image": _captcha_svg(answer)}


def check_captcha(db, token: str | None, answer: str | None) -> bool:
    """Valid signature + correct answer + never used before."""
    body = unsign(token, "c")
    if not body or not answer or not hmac.compare_digest(body["h"], _ans_hash(body["n"], answer)):
        return False
    try:
        db.captcha_used.insert_one({"_id": body["n"], "at": datetime.now(timezone.utc)})
    except Exception:  # noqa: BLE001  duplicate key => already used
        return False
    return True


def safe_equal(a: str, b: str) -> bool:
    """Constant-time string comparison (tokens, secrets)."""
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


# ------------------------------------------------------------------ rate limiting
class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(self._hits) > 20000:  # crude memory guard
            for k in [k for k, v in self._hits.items() if not v][:5000]:
                self._hits.pop(k, None)
        return True


limiter = RateLimiter()
