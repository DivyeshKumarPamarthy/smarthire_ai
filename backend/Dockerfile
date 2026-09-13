# SmartHire AI — backend
#
# Deliberately a Dockerfile rather than Render's native Python runtime. The
# native runtime is marginally simpler, but this app has to run somewhere that
# offers a persistent disk and real WebSockets, and pinning the image here
# means moving between Render, Fly, Railway or a VPS is a config change rather
# than a rebuild of how it is deployed.
#
# ONE WORKER, ALWAYS. metrics.py and ai_metrics.py hold their counters in
# process memory, so a second worker does not double the capacity — it splits
# the admin dashboard's view of the platform in half and presents one worker's
# numbers as the whole picture. Scale vertically, or move those counters out of
# memory first.

# 3.12 rather than the 3.14 used in local development. Nothing in this
# codebase or its dependencies needs anything newer — the highest stdlib
# feature in use is asyncio.to_thread (3.9), and every pinned package declares
# Requires-Python of 3.10 or lower. 3.12 is the safer base: it has had wheels
# built for it by everything on PyPI for years, whereas a 3.14 image can fail
# at pip install on any dependency that has not published a matching wheel yet.
FROM python:3.12-slim

# PYTHONUNBUFFERED so uvicorn's logs reach the platform's log viewer as they
# happen rather than when a buffer fills — the difference between watching a
# deploy and guessing at one.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements first so the dependency layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The upload directories are resolved relative to the working directory — see
# RESUME_UPLOAD_DIR / ANSWER_AUDIO_DIR / VIDEO_RECORDING_DIR in app/core/config.py.
# With WORKDIR /app they land in /app/uploads, which is where the persistent
# disk must be mounted. Created here so the app starts cleanly even before a
# disk is attached; an unmounted deploy then loses files on restart rather than
# crashing, which is the failure the checklist warns about.
RUN mkdir -p uploads/resumes uploads/answers uploads/recordings

# Non-root. The uploaded files are candidates' recordings of their own faces
# and voices; a container writing them as root is a needless amount of trust.
RUN useradd --create-home --uid 10001 smarthire \
 && chown -R smarthire:smarthire /app
USER smarthire

EXPOSE 8000

# $PORT is supplied by the platform; 8000 is the local fallback.
# --workers 1 is load-bearing, see the note at the top of this file.
# --timeout-keep-alive is raised because a voice interview holds a WebSocket
# open across a candidate's whole answer, and the default would cut it.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 120"]
