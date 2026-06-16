"""JWT issuing/verification and the identity resolver used by routes."""
import functools
from datetime import datetime, timedelta, timezone

import jwt
from flask import g, jsonify, request

import db
from config import JWT_EXPIRE_DAYS, JWT_SECRET


def make_token(user):
    payload = {
        "sub": str(user["_id"]),
        "username": user["username"],
        "role": user.get("role", "public"),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def current_user():
    """Return the logged-in user doc, or None for anonymous requests."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = decode_token(auth[7:])
    if not payload:
        return None
    return db.find_user(payload.get("username"))


def device_id():
    """Best-effort anonymous identity: a client-generated id, IP as fallback."""
    dev = request.headers.get("X-Device-Id")
    if not dev and request.is_json:
        dev = (request.json or {}).get("device_id")
    return dev or request.remote_addr or "unknown"


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "Login required."}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper
