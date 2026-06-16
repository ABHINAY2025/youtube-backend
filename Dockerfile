# ---------- Stage 1: build the React frontend ----------
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python backend + static frontend ----------
FROM python:3.12-slim

# ffmpeg is required for HD merging and MP3 extraction.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces run as uid 1000; create a matching user.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /home/user/app

COPY --chown=user backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user backend/ ./
# Drop the built SPA where Flask serves it from.
COPY --chown=user --from=frontend /build/dist ./static_frontend

EXPOSE 7860

# Single worker: the in-memory download-job table is not shared across
# workers. Threads handle concurrent polling/streaming. Long timeout so
# large file streams are not killed mid-transfer.
CMD ["gunicorn", "-w", "1", "--threads", "8", "--timeout", "600", "-b", "0.0.0.0:7860", "app:app"]
