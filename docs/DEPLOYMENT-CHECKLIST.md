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

## 6. Storage — no persistent disk on this deployment

**Decision, 2026-09-13: deploying without a persistent disk, deliberately.**

This is a portfolio and demo project. A persistent disk on Render requires a
paid instance, and the cost was judged not worth it for a deployment whose
purpose is to be shown working rather than to hold anyone's data. Durability
was traded away with eyes open.

### What this costs, concretely

Every file the platform stores lives only on the container's own filesystem:

- candidate **video recordings** of interview sessions
- **answer audio** for every question answered aloud
- uploaded **résumé PDFs**

All of it is destroyed on:

- every **restart**
- every **redeploy**
- the free tier's automatic **spin-down after 15 minutes of inactivity**

That last one is the surprising one. It needs no action from anyone — leave the
app alone over lunch and it happens by itself. A candidate who completes an
interview in the morning and returns in the afternoon finds their recordings
gone, while their **scores, transcripts and reports survive**, because those
live in Postgres rather than on disk.

- [ ] Understood and accepted for this deployment.

### No code change is needed, now or later

Verified rather than assumed: all three write sites — `app/api/resumes.py:63`,
`app/api/voice.py:168`, `app/api/interviews.py:644` — call
`directory.mkdir(parents=True, exist_ok=True)` immediately before writing.
`parents=True` builds the whole chain including `uploads/` itself, so a
container that boots with no `uploads` directory at all creates what it needs
on first write. Exercised against a filesystem with no `uploads/` present, which
is exactly the state a fresh ephemeral container starts in. The app starts
empty; it does not crash.

### Upgrading later

1. Switch `smarthire-api` to a paid instance (`plan: starter` or above).
2. Uncomment the `disk:` block in `render.yaml` — it is preserved there in full,
   with `mountPath: /app/uploads` already correct.
3. Redeploy.

**No application change is required.** The upload paths are relative and
already resolve to `/app/uploads` under the Dockerfile's `WORKDIR`. Files
written before the upgrade are gone; files written after it persist.

Note for whenever that happens: Render's persistent disks are **not backed up
by default**. Attaching a disk makes uploads survive restarts, not disasters.

---

## 6b. Database — free Postgres, and it has a deletion date

**Decision, 2026-09-13: free Postgres, deliberately.** Same reasoning as the
disk: a demo project, cost over durability.

**This one is not like the disk.** Without a disk, the app loses uploads on
every restart but keeps running indefinitely — an unpleasant steady state you
can live in forever. A free Postgres does not have a steady state. It has an
expiry date, and after it the data is gone permanently. **This is a task with a
deadline, not a tradeoff to accept once.**

### The timeline, from Render's own documentation

| Event | When |
|---|---|
| Database created | day 0 |
| **Expires** — becomes inaccessible | **day 30** |
| Grace period to upgrade | days 30–44 (**14 days**) |
| **Deleted, with all data** | **after day 44** |

Render emails before expiry and again before the grace period ends.

Beware stale numbers: free Postgres used to last **90 days**, and Render's
changelog records the change to 30. Anything citing 90 is out of date —
including, possibly, a half-remembered figure.

- [ ] **Record the real dates from the dashboard, here, once provisioned.**
      Do not trust the table above, including when it agrees with you. Open the
      database in Render, read the expiry date it actually shows for *this*
      instance, and write both dates in:

      - Created: `________`
      - Expires (day 30): `________`
      - Deleted after grace (day 44): `________`

- [ ] Put the **expiry date in a calendar**, not just in this file. A checklist
      is read while deploying; this deadline arrives a month later when nobody
      is reading it.

### What is lost at deletion

Everything that survives a restart today:

- every **user account** — candidates, recruiters, admins
- every **interview**, its questions, transcripts and answers
- every **score, rubric breakdown and report**
- every **notification**

The uploads are already ephemeral, so after day 44 there is nothing left of the
deployment but the code.

### Upgrading before expiry

Confirmed against Render's documentation, because "a plan change is surely
safe" is exactly the assumption worth checking for a live database: upgrading a
free Postgres to a paid compute plan **preserves the database and its data in
place**. It is not a create-and-migrate. This can be done during the grace
period as well as before expiry.

- [ ] Upgrade before day 44 if the data matters. There is no recovery
      afterwards — Render's docs describe no restore path for a deleted free
      database.

### Free web service spin-down

- [ ] **The free web service spins down after 15 minutes without traffic**, and
      takes **about a minute** to spin back up on the next request or WebSocket
      connection. Open the app a minute before demoing it to anyone.

That spin-down is also what destroys the uploads described in §6 — it is the
same event, and it needs nobody to do anything.

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
- [ ] Run one interview end to end and confirm it works while the service is
      live: questions served, answer recorded, report produced.
- [ ] Confirm the app **degrades gracefully** once storage is gone. Restart the
      service, then open that interview from history. Expected: the page loads,
      the score and transcript are still there from Postgres, and the missing
      recording is reported as unavailable — no crash, no 500. What is being
      checked is that absent files are handled, not that they survived; on this
      tier they are not supposed to.

      This should hold — both file endpoints guard for it. `get_recording`
      (`app/api/interviews.py:723`) and `get_answer_audio`
      (`app/api/interviews.py:404`) each test `path.is_file()` and raise **404,
      not 500**, when the row exists but the file does not; the frontend already
      renders that as "No camera recording was kept for this interview". The
      step is still worth running, because it is the difference between a guard
      that exists and a guard that works.
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
