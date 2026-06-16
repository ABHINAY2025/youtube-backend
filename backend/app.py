"""devX Video Downloader — API + static React host.

Run locally:   python app.py
Production:    gunicorn -w 1 --threads 8 -b 0.0.0.0:7860 app:app
               (single worker: the in-memory job table is not shared)
"""
import os

from flask import Flask, g, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

import db
import downloader as dl
from auth import current_user, device_id, login_required, make_token

# The React build is copied here by the Dockerfile.
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "static_frontend")

app = Flask(__name__, static_folder=None)
CORS(app)  # allow the Vite dev server during local development

try:
    db.init_db()
except Exception as exc:  # noqa: BLE001 - surface clearly, keep app importable
    print(f"[WARN] MongoDB not initialised: {exc}")


# ----- helpers -----------------------------------------------------------
def _quota_state():
    """Resolve who is asking and how many downloads they have left.

    Returns (kind, key, remaining, user) where remaining is None for
    unlimited (admin) and an int otherwise.
    """
    user = current_user()
    if user:
        rem = db.remaining_for_user(user)
        return "user", str(user["_id"]), rem, user
    dev = device_id()
    return "anon", dev, db.remaining_for_anon(dev), None


# ----- auth --------------------------------------------------------------
@app.post("/api/auth/register")
def register():
    body = request.json or {}
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    if len(username) < 3 or len(password) < 6:
        return jsonify({"error": "Username (3+) and password (6+) required."}), 400
    if db.find_user(username):
        return jsonify({"error": "That username is taken."}), 409
    user = db.create_user(username, generate_password_hash(password), role="public")
    return jsonify({"token": make_token(user), "username": username, "role": "public"})


@app.post("/api/auth/login")
def login():
    body = request.json or {}
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    user = db.find_user(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401
    return jsonify({
        "token": make_token(user),
        "username": user["username"],
        "role": user.get("role", "public"),
    })


@app.get("/api/me")
def me():
    user = current_user()
    if user:
        return jsonify({
            "authenticated": True,
            "username": user["username"],
            "role": user.get("role", "public"),
            "remaining": db.remaining_for_user(user),  # None => unlimited
        })
    dev = device_id()
    return jsonify({
        "authenticated": False,
        "remaining": db.remaining_for_anon(dev),
    })


# ----- video info & download --------------------------------------------
@app.post("/api/info")
def info():
    url = ((request.json or {}).get("url") or "").strip()
    if not url:
        return jsonify({"error": "Please provide a URL."}), 400
    try:
        return jsonify(dl.probe(url))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Could not read this link: {exc}"}), 400


@app.post("/api/download")
def download():
    body = request.json or {}
    url = (body.get("url") or "").strip()
    fmt = (body.get("format_id") or "").strip()
    mode = body.get("mode", "progressive")
    if not url or not fmt:
        return jsonify({"error": "Missing url or format."}), 400

    kind, key, remaining, user = _quota_state()
    if remaining is not None and remaining <= 0:
        if kind == "anon":
            return jsonify({
                "error": "You've used your 2 free downloads. Please register to continue.",
                "code": "register_required",
            }), 401
        return jsonify({
            "error": "Daily limit reached (2/day). Try again tomorrow.",
            "code": "daily_limit",
        }), 429

    # Record usage only once the file is actually ready (a failed fetch
    # should not burn a quota).
    def on_success():
        db.record_usage(kind, key, url)

    job_id = dl.start_job(url, fmt, mode, on_success=on_success if remaining is not None else None)
    return jsonify({"job_id": job_id})


@app.get("/api/progress/<job_id>")
def progress(job_id):
    job = dl.public_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job."}), 404
    return jsonify(job)


@app.get("/api/file/<job_id>")
def file(job_id):
    job = dl.get_job(job_id)
    if not job or job.get("status") != "ready":
        return jsonify({"error": "File not ready."}), 404
    dl.schedule_cleanup(job_id, delay=120)
    return send_file(job["filepath"], as_attachment=True,
                     download_name=job["download_name"])


# ----- serve the React SPA ----------------------------------------------
@app.get("/")
@app.get("/<path:path>")
def spa(path=""):
    full = os.path.join(FRONTEND_DIR, path)
    if path and os.path.isfile(full):
        return send_from_directory(FRONTEND_DIR, path)
    index = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(index):
        return send_from_directory(FRONTEND_DIR, "index.html")
    return jsonify({"status": "API running. Build the frontend to serve the UI."})


if __name__ == "__main__":
    print(f"ffmpeg available: {dl.FFMPEG_AVAILABLE}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "7860")), debug=True)
