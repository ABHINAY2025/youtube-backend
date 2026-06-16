"""MongoDB access layer: connection, admin seeding, and quota tracking.

Documents
---------
ytdl_users:
    { _id, username, password_hash, role: "admin"|"public", created_at }
ytdl_usage:
    { _id, kind: "anon"|"user", key, url, day: "YYYY-MM-DD", ts }
    * anon  -> key is the device id; counted for all time (lifetime limit)
    * user  -> key is the user id; counted per `day` (daily limit)
"""
from datetime import datetime, timezone

from pymongo import MongoClient
from werkzeug.security import check_password_hash, generate_password_hash

from config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    ANON_LIMIT,
    COLL_USAGE,
    COLL_USERS,
    MONGO_URI,
    USER_DAILY_LIMIT,
)

_client = None
_db = None


def init_db(client=None):
    """Connect (or accept an injected client for tests) and seed the admin."""
    global _client, _db
    if client is not None:
        _client = client
    else:
        if not MONGO_URI:
            raise RuntimeError("MONGO_URI is not set.")
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
    _db = _client.get_default_database()
    _ensure_indexes()
    seed_admin()
    return _db


def get_db():
    if _db is None:
        init_db()
    return _db


def _ensure_indexes():
    _db[COLL_USERS].create_index("username", unique=True)
    _db[COLL_USAGE].create_index([("kind", 1), ("key", 1), ("day", 1)])


def seed_admin():
    """Ensure the admin account exists and matches the ADMIN_PASSWORD secret.

    The secret is the single source of truth: to rotate the admin password,
    change the ADMIN_PASSWORD secret and restart the Space. On boot we only
    rewrite the hash when the stored one no longer matches the secret, so a
    normal restart is a cheap no-op.
    """
    users = _db[COLL_USERS]
    admin = users.find_one({"username": ADMIN_USERNAME})
    if admin is None:
        users.insert_one({
            "username": ADMIN_USERNAME,
            "password_hash": generate_password_hash(ADMIN_PASSWORD),
            "role": "admin",
            "created_at": datetime.now(timezone.utc),
        })
    elif not check_password_hash(admin["password_hash"], ADMIN_PASSWORD):
        users.update_one(
            {"_id": admin["_id"]},
            {"$set": {
                "password_hash": generate_password_hash(ADMIN_PASSWORD),
                "role": "admin",
            }},
        )


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ----- users -------------------------------------------------------------
def find_user(username):
    return get_db()[COLL_USERS].find_one({"username": username})


def create_user(username, password_hash, role="public"):
    doc = {
        "username": username,
        "password_hash": password_hash,
        "role": role,
        "created_at": datetime.now(timezone.utc),
    }
    res = get_db()[COLL_USERS].insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


# ----- quota -------------------------------------------------------------
def anon_count(device_id):
    return get_db()[COLL_USAGE].count_documents({"kind": "anon", "key": device_id})


def user_count_today(user_id):
    return get_db()[COLL_USAGE].count_documents(
        {"kind": "user", "key": str(user_id), "day": _today()}
    )


def record_usage(kind, key, url=""):
    get_db()[COLL_USAGE].insert_one({
        "kind": kind,
        "key": str(key),
        "url": url,
        "day": _today(),
        "ts": datetime.now(timezone.utc),
    })


def remaining_for_anon(device_id):
    return max(0, ANON_LIMIT - anon_count(device_id))


def remaining_for_user(user):
    if user.get("role") == "admin":
        return None  # unlimited
    return max(0, USER_DAILY_LIMIT - user_count_today(user["_id"]))
