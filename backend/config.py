"""Central configuration, read from environment variables.

On Hugging Face Spaces these are set as *Secrets* in the Space settings.
Locally they come from a .env file (see .env.example).
"""
import os

from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI", "")
# Collections live inside the database named in the URI (here: "news"),
# but are prefixed so they never collide with other apps using that DB.
COLL_USERS = "ytdl_users"
COLL_USAGE = "ytdl_usage"

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "7"))

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# Download limits.
ANON_LIMIT = int(os.environ.get("ANON_LIMIT", "2"))          # lifetime, per device
USER_DAILY_LIMIT = int(os.environ.get("USER_DAILY_LIMIT", "2"))  # per day, per account

# Optional: residential proxy for yt-dlp (the scaling fix described in the
# README). Leave empty for direct connections.
YTDLP_PROXY = os.environ.get("YTDLP_PROXY", "")
# Optional path to a cookies.txt for restricted/age-gated videos.
YTDLP_COOKIES = os.environ.get("YTDLP_COOKIES", "")
