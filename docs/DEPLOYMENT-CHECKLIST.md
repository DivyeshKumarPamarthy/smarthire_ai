# Deployment checklist — SmartHire AI

Work through this in order. It is written for Render (`render.yaml` at the
repository root), but only steps 4 and 5 are Render-specific — the rest apply
to any host.

Nothing in this repository deploys itself, and one step below is the difference
between a working deployment and one that signs authentication tokens with a
key published in the source.

---

## 1. JWT secret — do this first, and separately

**Already fixed in code; this is the deployment half.**

`app/core/config.py` ships `JWT_SECRET_KEY = "insecure-dev-key-change-me"` as
its default. Anyone who can read the repository can read that key, and a
deployment using it lets them mint a valid token for any account, including an
administrator. The application works perfectly with it, which is why this fails
silently.

- [ ] Generate a secret:
      `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- [ ] Set it as `JWT_SECRET_KEY` **in the host's environment variable UI**, not
      in any file in this repository.
- [ ] Set `ENVIRONMENT=production`.

`ENVIRONMENT=production` makes a missing or default secret a **startup error**
rather than a warning — the app refuses to boot. That is deliberate: a
deployment that will not start gets fixed in minutes, and a warning in a log
nobody reads does not.

Verify locally before deploying:

```bash
ENVIRONMENT=production JWT_SECRET_KEY=insecure-dev-key-change-me \
  python -c "import app.main"     # must raise RuntimeError
```

Rotating this later logs every signed-in user out. Fine now, worth knowing.

---

## 2. Database and migrations

- [ ] Provision Postgres and set `DATABASE_URL`.

SQLite is the default in `config.py` for local convenience only. It has no
place anywhere holding more than one candidate's data.

### On a fresh database the migration scripts are no-ops — run them anyway

This repository has **no Alembic**. Schema comes from
`Base.metadata.create_all` at startup (`app/main.py`), which creates missing
*tables* from the current models but never alters an existing one.

On a **fresh** database that is enough: `create_all` builds every table from
today's models, and those models already contain every column the scripts in
`backend/scripts/` were written to add. Verified — all of
`behavior_report`, `overall_score`, `session_id`, the pause columns, the answer
audio columns, the analysis columns and `email_notifications` are present in
the models and therefore in a freshly created schema.

Run them regardless. All eight are idempotent, each checks its table exists
before touching anything, and each prints `already present` and exits when
there is nothing to do. They cost seconds and they turn an assumption into a
confirmation.

- [ ] **Boot the app once first.** The scripts ALTER tables; `create_all` is
      what creates them. Run them against an empty database and every one
      reports that its table does not exist yet.
- [ ] Then run all eight. Order between them does not matter — each is
      independent and self-guarding — but this is the chronological order they
      were written in, which is the order to use if anything does go wrong:

```bash
python -m scripts.add_session_id_column
python -m scripts.add_interview_score_column
python -m scripts.add_session_pause_columns
python -m scripts.add_session_analysis_columns
python -m scripts.add_answer_audio_columns
python -m scripts.add_recording_tables
python -m scripts.add_interview_behavior_report_column
python -m scripts.add_user_email_notifications_column
```

- [ ] Confirm the output is eight lines of `already present` (fresh database)
      or a mix of `added` and `already present` (existing database). Anything
      saying a table **does not exist yet** means the app has not booted
      against this database — go back and boot it.

**Migrating an existing database instead of a fresh one?** Then these are not
optional and not no-ops. `add_user_email_notifications_column` in particular is
the one that matters most recently: without it every request touching a user
row fails, because the model declares a column the table does not have.

---

## 3. The Gemini quota decision — make it before going live, not after

Google's free tier allows **20 requests per day per model**. Module 5 spends
one per answer. A single eight-question interview consumes nearly half of it,
after which transcription stops and candidates' interviews are recorded but
never scored.

This is not hypothetical: it happened during development and went unnoticed for
a day, because a spent quota looked identical to everything working. The admin
dashboard's AI monitoring (Module 10) now surfaces it, but only once it has
already happened.

Choose one, explicitly:

- [ ] **Add billing** to the Google Cloud project. The only option that scales.
- [ ] **Add more keys** — set `GEMINI_API_KEYS` to a comma-separated list. The
      provider fails over on quota exhaustion and sticks to whichever key
      works. Use only keys you are entitled to; extra projects created to
      multiply the free allowance are against Google's terms.
- [ ] **Turn analysis off** — `ANALYSE_ANSWERS=false`. Interviews run and
      recordings are stored; nothing is transcribed or scored. A legitimate
      choice for a demo, and the honest one if no billing is available.

Doing none of these means choosing the third by accident, a few interviews in.

---

## 4. Email — inert until configured

Notifications are recorded and shown in-app whether or not email works; they
are marked *"not emailed — no mail server configured"* rather than silently
dropped. So this is optional, but leaving it unset is a decision.

- [ ] Set `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`.
- [ ] Gmail requires an **App Password**, not an account password — it rejects
      account passwords over SMTP. Generate one at
      `myaccount.google.com/apppasswords` with 2-Step Verification enabled.

No message has ever been sent from this codebase. The skip path and the failure
path are tested against a fake transport; the first real send is unproven.

---

## 5. Frontend origin — both variables, both to the real origin

- [ ] `FRONTEND_URL` and `BACKEND_CORS_ORIGINS` must be the deployed
      frontend's origin. `render.yaml` wires both from the static site, so this
      is automatic there and manual anywhere else.
- [ ] `VITE_API_URL` is baked into the bundle **at build time** by Vite, not
      read at runtime. Changing it needs a rebuild, not a restart, and the same
      build cannot be promoted between environments.

Left at localhost, every API call is blocked by the browser and the app appears
broken with nothing wrong in the server logs.

---

## 6. Persistent disk

- [ ] Disk mounted at **`/app/uploads`**, 1 GB to start.

The upload paths in `config.py` are relative, so with the Dockerfile's
`WORKDIR /app` they resolve to `/app/uploads`. Mount anywhere else and the app
writes into the container's own filesystem and loses every recording on
restart — **with no error at all**, which makes it the worst failure available
here.

- [ ] **The uploads disk has no backup by default.** Render's persistent disks
      are not snapshotted unless you configure it. Every candidate's audio and
      video lives only there, and a lost disk loses all of it permanently. Not
      being fixed now — recorded so it is a choice rather than a gap discovered
      later.

Current local footprint is 376 MB and it only grows: every interview adds audio
per answer plus a session video, and there is no retention policy. Watch it.

---

## 7. One instance, deliberately

- [ ] Keep `numInstances: 1` and `--workers 1`.

`metrics.py` and `ai_metrics.py` hold their counters in process memory. A
second worker does not share them — it splits them, and the admin dashboard
then presents one worker's view of the platform as the whole picture. Scale
vertically until those counters live somewhere shared.

---

## After deploying

- [ ] `GET /api/health` returns healthy and reports the expected AI provider.
- [ ] Sign in as each of the three roles.
- [ ] Run one interview end to end and confirm the recording survives a manual
      service restart. This is the check that proves the disk is really mounted
      — and the one most worth doing, because the failure it catches is silent.
- [ ] Check the admin dashboard's AI monitoring shows calls being counted.

## Known gaps, carried in deliberately

- **No CI.** Nothing runs the 512-test suite automatically. Run it before
  deploying: `python -m pytest tests/ -q`.
- **No frontend regression tests.** This repository has no frontend test
  harness; UI behaviour has been verified by scripted browser walkthroughs, not
  by a suite that will catch a future break.
- **Reminders do not fire on their own.** There is no worker process, so
  interview reminders are computed when the endpoint is called.
- **AI monitoring resets on restart.** In-memory by design; it cannot answer
  "what happened last Tuesday".
