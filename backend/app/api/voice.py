"""
Feature 9 — the real-time voice interviewer.

Why voice rather than a written test: the candidate must answer out loud, so
they cannot paste a question into a chatbot and read back the answer.

Questions are delivered as text — there is no text-to-speech. The candidate's
answer is kept as the recording the browser captured, which stays the primary
artefact: exactly what they said, in their own voice.

Module 5 then transcribes that recording, analyses it, and scores it against
a fixed rubric off the same transcript. The transcript is stored
*alongside* the audio, never instead of it, so the machine's guess at what was
said can always be checked against the recording — and an outage in the
speech service costs the transcript and the score, never the answer.

Protocol (JSON text frames over a WebSocket):

    connect   ws://HOST/api/interviews/voice/{interview_id}?token=<JWT>

    server -> {"type":"ready","interview_id":1,"total":5,"answered":0,
               "skipped":0,"interview_type":"HR","domain":"...",
               "difficulty":"EASY"}

    client -> {"type":"next"}
    server -> {"type":"question","sequence_no":1,"category":"Introduction",
               "text":"..."}

    client -> {"type":"answer","audio_b64":"<base64>","mime_type":"audio/webm",
               "duration_seconds":42.5}
    server -> {"type":"recorded","sequence_no":1,"bytes":48213,
               "analysis_pending":true,"answered":1,"skipped":0,"total":5}
    server -> {"type":"transcript","sequence_no":1,"transcript":"..."}
    server -> {"type":"analysis","sequence_no":1,"transcript":"...",
               "fillers":{...},"pace":{...},"communication":{...},
               "pronunciation":{...},
               "score":{"available":true,"communication":78,"confidence":65,
                        "technical_relevance":80,"professionalism":90,
                        "overall":76.5,"rating":"Good","rationale":"..."}}

`duration_seconds` is the browser's measured recording length. It is what pace
is computed from — see the column comment on answer_duration_seconds for why
the asked-to-answered interval will not do.

`transcript` and `analysis` are produced by a background task, so they are the
one part of this protocol that is NOT ordered against the rest: the candidate
can ask for the next question while the previous answer is still being
transcribed, and its frames then arrive after that next `question` frame. Both
carry `sequence_no` for exactly this reason, and a client must match on it
rather than assuming the newest frame describes the question on screen. This is
deliberate — awaiting the analysis inline blocked the receive loop, so `next`
went unread until transcription and scoring had finished and the button looked
dead. Nothing is scored or closed out with an analysis still in flight.

`recorded` is sent as soon as the audio is on disk; `transcript` follows once
the speech model has answered and the result has passed the plausibility check;
`analysis` follows that, once grammar, pronunciation and scoring are done. The
transcript is repeated on the `analysis` frame, so `transcript` is purely an
earlier chance to show the candidate their own words — it exists because
grading is slow and can fail, and neither should decide whether someone gets to
read back what they said. A client that ignores both still runs a complete
interview.

    client -> {"type":"pause"}       # stop the clock
    server -> {"type":"paused","interview_id":1,"total_paused_seconds":0}
    client -> {"type":"resume"}
    server -> {"type":"resumed","interview_id":1,"total_paused_seconds":94}

    client -> {"type":"skip"}        # pass on this one
    server -> {"type":"skipped","sequence_no":2,"attempted":false,
               "answered":1,"skipped":1,"total":5}
    server -> {"type":"question", ...}   # the next one, unprompted

    client -> {"type":"next"} ...    # until every question is done
    server -> {"type":"complete","interview_id":1,"answered":4,"skipped":1,
               "total":5,"score":{"available":true,"overall":76.5,
                                  "rating":"Good"}}

    errors -> {"type":"error","detail":"..."}

`score` on `complete`/`closed` is the interview's overall — the average of its
answered questions' scores (app.services.scoring), stamped onto
Interview.overall_score at the same moment. {"available":false} when nothing
was ever scored: analysis disabled, every provider call failed, or every
question was skipped.

A skip advances the interview on its own — the client does not send `next`
afterwards. Skipped questions are *not attempted*: they never count towards
`answered`, and they are not asked again.

While paused, `next`, `answer` and `skip` are refused: without that, a
candidate could read ahead on a stopped clock. `end` still works, so someone
who steps away and decides not to come back need not resume just to stop.
`end` sets a terminal status — it is a decision, not a disconnection.

Recordings are played back over the sibling REST route in interviews.py:
GET /api/interviews/{id}/answers/{sequence_no}/audio

Close codes: 4401 bad/missing token, 4404 interview not found, 4409 interview
has no questions.
"""

import asyncio
import base64
import binascii
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketState

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import SessionLocal, get_db
from app.models.interview import (
    QUESTION_ANSWERED,
    QUESTION_HANDLED,
    QUESTION_SKIPPED,
    Interview,
    InterviewQuestion,
    SessionStatus,
)
from app.models.setting import get_settings
from app.models.user import User
from app.services import ai_provider, scoring, speech_analysis
from app.services.session_timing import finalise_duration, per_question_seconds
from app.services.ai_provider import AIUnavailable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interviews", tags=["interviews-voice"])

# Guard against a client streaming an enormous blob into memory. Base64 inflates
# by ~4/3, so the cap is applied to the encoded string before it is decoded.
def _max_b64_chars() -> int:
    return (settings.MAX_ANSWER_AUDIO_MB * 1024 * 1024 * 4) // 3


# What a browser's MediaRecorder actually produces, plus wav for the bundled
# test client. The mime type decides the file extension, so it is matched
# against this table rather than trusted — it arrives from the client.
AUDIO_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


def _store_answer_audio(audio: bytes, mime_type: str, interview_id: int) -> tuple[str, str]:
    """
    Write a recording to disk and return (relative path, normalised mime type).

    The filename is chosen here, never taken from the client, and the extension
    comes from the lookup table above — so an unrecognised mime type lands as
    .bin rather than as whatever the caller asked for.
    """
    mime = (mime_type or "").split(";")[0].strip().lower()
    extension = AUDIO_EXTENSIONS.get(mime, ".bin")

    directory = Path(settings.ANSWER_AUDIO_DIR) / str(interview_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{uuid.uuid4()}{extension}"
    destination.write_bytes(audio)
    return str(destination), mime or "application/octet-stream"


def _duration(raw) -> Optional[float]:
    """
    The client's measured speaking time, sanity-checked.

    It arrives from the browser, so it is a claim rather than a fact. A
    negative or absurd value would produce a nonsense words-per-minute figure,
    and a wrong number here is worse than no number — pace is reported as
    unavailable when this comes back None.
    """
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    # Longer than the audio size cap could plausibly hold, so it is not real.
    if seconds <= 0 or seconds > 60 * 60:
        return None
    return round(seconds, 2)


async def _try_send(websocket: WebSocket, payload: dict) -> bool:
    """
    Send a frame, or give up quietly if the candidate has already gone.

    Analysis now runs in the background and outlives the socket: a candidate
    who finishes and navigates away leaves a transcription still in flight,
    which then tries to report into a closed connection. That used to raise
    `Unexpected ASGI message 'websocket.send', after sending 'websocket.close'`
    and take the whole handler down with it — losing the analysis of every
    other answer still running. A disconnected candidate is a normal way for an
    interview to end, not an error, so it is logged and swallowed.
    """
    if websocket.client_state != WebSocketState.CONNECTED:
        return False
    try:
        await websocket.send_json(payload)
        return True
    except (RuntimeError, WebSocketDisconnect):
        logger.info("Dropped a frame for a websocket that had already closed.")
        return False


async def _analyse_answer(
    websocket: WebSocket,
    interview_id: int,
    question_id: int,
    audio: bytes,
    mime: str,
) -> None:
    """
    Module 5: transcribe the recording, analyse it, store both, report back.

    Runs strictly after the audio is on disk and committed. Everything in here
    is best-effort — the recording is the primary artefact and must survive a
    transcription outage, a spent quota or a malformed response. A failure
    costs the transcript and the analysis, never the answer.

    Runs as a background task, NOT inline in the receive loop. Awaiting it
    there meant the server could not read another client message until every
    provider call had finished: the candidate saw "Next question" light up (the
    `recorded` frame had arrived), clicked it, and nothing happened for as long
    as transcription and scoring took — which reads as a broken button, and on
    a spent quota never resolved at all.

    Because it outlives the loop's turn, it takes ids rather than ORM objects
    and opens its own Session. Sharing the request's session would mean two
    coroutines committing through one SQLAlchemy Session concurrently, which is
    not safe. The provider calls themselves are synchronous and slow, so they
    still go through asyncio.to_thread to keep the event loop free.
    """
    with SessionLocal() as db:
        question = (
            db.query(InterviewQuestion)
            .filter(InterviewQuestion.id == question_id)
            .first()
        )
        interview = db.query(Interview).filter(Interview.id == interview_id).first()
        if question is None or interview is None:
            logger.warning("Answer analysis skipped: question %s is gone.", question_id)
            return

        sequence_no = question.sequence_no

        try:
            transcript = await asyncio.to_thread(ai_provider.speech_to_text, audio, mime)
        except AIUnavailable as exc:
            logger.warning("Transcription unavailable for question %s: %s", question_id, exc)
            await _try_send(
                websocket,
                {
                    "type": "analysis",
                    "sequence_no": sequence_no,
                    "available": False,
                    "reason": str(exc),
                },
            )
            return
        except Exception:  # noqa: BLE001
            logger.exception("Transcription failed for question %s", question_id)
            await _try_send(
                websocket,
                {
                    "type": "analysis",
                    "sequence_no": sequence_no,
                    "available": False,
                    "reason": "The answer was recorded, but it could not be transcribed.",
                },
            )
            return

        # Before the transcript is stored or shown, check it could physically
        # have been said in the recording's length. The speech model invents
        # fluent answers for audio it cannot make out, and an invented
        # transcript attached to a candidate's interview is worse than no
        # transcript at all — so a failed check discards it rather than storing
        # it with a caveat.
        plausible, reason = speech_analysis.transcript_is_plausible(
            transcript, question.answer_duration_seconds
        )
        if not plausible:
            logger.warning(
                "Discarding implausible transcript for question %s: %s", question_id, reason
            )
            question.analysis = {"available": False, "reason": reason}
            question.analyzed_at = datetime.now(timezone.utc)
            db.commit()
            await _try_send(
                websocket,
                {
                    "type": "analysis",
                    "sequence_no": sequence_no,
                    "available": False,
                    "reason": reason,
                },
            )
            return

        # An empty transcript is a real outcome, not a failure: the candidate
        # may have recorded silence. Saying so is more useful than a generic
        # error.
        question.answer_text = transcript
        db.commit()

        # Hand the candidate their own words the moment they exist, rather than
        # holding them behind grading.
        #
        # Everything after this point is slow and can fail: two more cloud calls
        # and a local model, any of which can spend a quota or time out. None of
        # that changes what was said, so none of it should gate showing it. The
        # same transcript is repeated on the `analysis` frame below — this is
        # additive, so a client that ignores this frame behaves exactly as before.
        #
        # Sent only once the plausibility check above has passed: an invented
        # transcript is worse than a late one, and this must never show text that
        # the checks would go on to discard.
        await _try_send(
            websocket,
            {
                "type": "transcript",
                "sequence_no": sequence_no,
                "transcript": transcript,
            },
        )

        try:
            analysis = await asyncio.to_thread(
                speech_analysis.analyse_answer,
                question_text=question.question_text,
                transcript=transcript,
                duration_seconds=question.answer_duration_seconds,
                audio=audio,
                audio_mime=mime,
                interview_type=interview.interview_type.value,
                domain=interview.domain,
                difficulty=interview.difficulty.value,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Answer analysis failed for question %s", question_id)
            analysis = {
                "available": False,
                "reason": "The answer was transcribed, but the analysis could not be completed.",
            }

        question.analysis = analysis
        question.analyzed_at = datetime.now(timezone.utc)
        db.commit()

        await _try_send(
            websocket,
            {
                "type": "analysis",
                "sequence_no": sequence_no,
                "transcript": transcript,
                **analysis,
            },
        )


def _authenticate(token: Optional[str], db: Session) -> Optional[User]:
    """
    Resolve the ?token= query parameter into a User.

    The token is in the query string rather than an Authorization header
    because the browser WebSocket API cannot set custom headers. It is the same
    JWT the REST endpoints use.
    """
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    user_id = payload.get("id")
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def _next_question(db: Session, interview_id: int) -> Optional[InterviewQuestion]:
    """
    The lowest-numbered question the candidate has not dealt with yet.

    Skipped questions count as dealt with, so passing on one moves the
    interview forward instead of serving it again.
    """
    return (
        db.query(InterviewQuestion)
        .filter(InterviewQuestion.interview_id == interview_id, ~QUESTION_HANDLED)
        .order_by(InterviewQuestion.sequence_no)
        .first()
    )


def _progress(db: Session, interview_id: int) -> dict:
    """
    How far along the interview is.

    `answered` counts only questions the candidate actually attempted. Skips are
    reported separately as `skipped` and never inflate the answered figure — a
    question passed on is not attempted, and the numbers must say so.
    """
    asked = db.query(InterviewQuestion).filter(
        InterviewQuestion.interview_id == interview_id
    )
    return {
        "total": asked.count(),
        "answered": asked.filter(QUESTION_ANSWERED).count(),
        "skipped": asked.filter(QUESTION_SKIPPED).count(),
    }


def _score_interview(db: Session, interview: Interview) -> dict:
    """
    Module 5: stamp the interview's overall score as it completes.

    Called from both places an interview reaches COMPLETED — running out of
    questions and an explicit `end` — so neither path can leave a finished
    interview unscored. Queried directly rather than via interview.questions,
    which may be stale in this session by the time the last answer's score
    was committed a moment ago.

    Returns the same shape scoring.aggregate_score's caller in the analytics
    endpoint uses, so the client can show the result immediately without a
    second round trip.
    """
    analyses = [
        row[0]
        for row in db.query(InterviewQuestion.analysis)
        .filter(InterviewQuestion.interview_id == interview.id)
        .all()
    ]
    overall = scoring.aggregate_score(
        analyses,
        scoring.time_management_score(interview),
    )
    interview.overall_score = overall
    _notify_report_ready(db, interview)
    if overall is None:
        return {"available": False}
    return {"available": True, "overall": overall, "rating": scoring.rating_label(overall)}


def _notify_report_ready(db: Session, interview: Interview) -> None:
    """
    Module 9: tell the candidate their report exists.

    Best-effort in the strongest sense — this runs at the moment an interview
    is finalised, and a notification failing must never cost the candidate the
    completion itself. Anything that goes wrong here is logged and swallowed.

    Deliberately fires whether or not a score was produced: "recorded but not
    scored" is exactly the case a candidate most needs telling about, and only
    notifying on success would leave them waiting for a report that is never
    coming.
    """
    try:
        from app.models.notification import NotificationKind
        from app.models.user import Role, User
        from app.services import notifications as notify_service

        user = db.query(User).filter(User.id == interview.user_id).first()
        if user is None:
            return

        # The candidate: their own report.
        title, body = notify_service.compose_report_ready(interview)
        notify_service.notify(
            db, user,
            kind=NotificationKind.REPORT_READY,
            title=title, body=body,
            interview_id=interview.id,
            # Automated, because this is transactional mail about the
            # candidate's own interview. Their email_notifications switch is
            # honoured inside notify(), and nothing sends at all until
            # SMTP_HOST is configured.
            send_email=True,
        )

        # Recruiters: a candidate finished something worth reviewing. Sent to
        # the role rather than to an owner, because this schema has no
        # recruiter-to-candidate assignment to address it to.
        #
        # KNOWN SCALING GAP, deliberately left. This fans out one notification
        # per recruiter per completion, unbatched — unlike the stalled-interview
        # reminder, which is digested. The asymmetry is intentional: a stalled
        # reminder answers "what has been sitting?", which is a backlog question
        # and reads well as a digest, whereas a completion is an event whose
        # value is promptness. Collecting completions into a digest that only
        # materialises when someone pulls it would mean a recruiter sees nothing
        # until they press a button, which is a worse feature, not a better one.
        #
        # The part that actually hurts at scale is the email rather than the
        # feed row: fifty entries are browsable, fifty emails are spam. Fixing
        # that properly needs a scheduler this platform does not have — a
        # periodic job that rolls the completions since its last run into one
        # message per recruiter, leaving the in-app alerts real-time. Until
        # there is one, the honest options are this or nothing.
        #
        # Recruiters who do not want the mail can switch it off; notify()
        # honours their email_notifications preference.
        title, body = notify_service.compose_interview_completed(user.name, interview)
        notify_service.notify_role(
            db, Role.RECRUITER,
            kind=NotificationKind.SESSION_ALERT,
            title=title, body=body,
            interview_id=interview.id,
            send_email=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Could not raise the report-ready notification for interview %s",
            interview.id,
        )


_DEMO_PAGE = """<!doctype html>
<meta charset="utf-8"><title>SmartHire AI — voice interview demo</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 16px;
      background:#0d0d12;color:#e4e1e9}
 input,button,select{font:inherit;padding:8px 10px;margin:4px 4px 4px 0;border-radius:6px;
      border:1px solid #2e2e42;background:#1a1a24;color:#e4e1e9}
 button{cursor:pointer;background:#00c8ff;color:#04121a;border:0;font-weight:600}
 button:disabled{opacity:.4;cursor:not-allowed}
 #log{white-space:pre-wrap;background:#13131a;border:1px solid #252535;border-radius:6px;
      padding:14px;margin-top:16px;min-height:220px;font-size:14px;line-height:1.55}
 .q{color:#00c8ff;font-weight:600} .a{color:#00e87a} .e{color:#ff4d4d}
 fieldset{border:1px solid #252535;border-radius:6px;margin-bottom:12px}
</style>
<h2>SmartHire AI — real-time voice interview</h2>
<p style="color:#8d8a99;font-size:14px">Questions are shown as text. Your spoken
answer is recorded and stored as audio — nothing is transcribed.</p>
<fieldset><legend>1. Sign in</legend>
  <input id="email" value="candidate.demo@smarthire.dev" size="30">
  <input id="password" type="password" value="Candidate@123" size="18">
  <button onclick="doLogin()">Log in</button>
</fieldset>
<fieldset><legend>2. Pick or create an interview</legend>
  <input id="iid" placeholder="existing interview id" size="12">
  <select id="itype"><option>HR</option><option>TECHNICAL</option>
    <option>BEHAVIORAL</option><option>APTITUDE</option></select>
  <select id="idiff"><option>EASY</option><option>MEDIUM</option><option>HARD</option></select>
  <input id="idomain" value="hr executive" size="20">
  <button onclick="doGenerate()">Generate new</button>
</fieldset>
<fieldset><legend>3. Interview</legend>
  <button id="connect" onclick="connect()">Connect</button>
  <button id="next" onclick="askNext()" disabled>Next question</button>
  <button id="rec" onclick="toggleRec()" disabled>Hold to answer</button>
  <button id="skip" onclick="send({type:'skip'})" disabled>Skip</button>
</fieldset>
<div id="log">Log in, generate an interview, then Connect.</div>
<script>
let token=null, ws=null, rec=null, chunks=[], recording=false;
const $=i=>document.getElementById(i);
const log=(m,c)=>{const d=document.createElement('div');if(c)d.className=c;d.textContent=m;
  $('log').appendChild(d);$('log').scrollTop=1e9;};
const api=p=>location.origin+'/api'+p;

async function doLogin(){
  const r=await fetch(api('/auth/login'),{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({email:$('email').value,password:$('password').value})});
  if(!r.ok){log('login failed: '+r.status,'e');return;}
  token=(await r.json()).access_token; log('logged in');
}
async function doGenerate(){
  if(!token)return log('log in first','e');
  const r=await fetch(api('/interviews/generate'),{method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},
    body:JSON.stringify({interview_type:$('itype').value,domain:$('idomain').value,
      difficulty:$('idiff').value,question_count:5})});
  if(!r.ok){log('generate failed: '+r.status,'e');return;}
  const b=await r.json(); $('iid').value=b.id;
  log(`created interview ${b.id} — ${b.question_count} questions (source: ${b.source})`);
}
function connect(){
  if(!token)return log('log in first','e');
  const id=$('iid').value; if(!id)return log('need an interview id','e');
  ws=new WebSocket(`${location.origin.replace('http','ws')}/api/interviews/voice/${id}?token=${encodeURIComponent(token)}`);
  ws.onmessage=onMessage;
  ws.onclose=()=>{log('— connection closed —');['next','rec','skip'].forEach(b=>$(b).disabled=true);};
  ws.onerror=()=>log('websocket error','e');
}
function send(o){ws&&ws.readyState===1&&ws.send(JSON.stringify(o));}
function askNext(){send({type:'next'});}
async function onMessage(ev){
  const m=JSON.parse(ev.data);
  if(m.type==='ready'){log(`ready — ${m.interview_type}/${m.difficulty}/${m.domain} (${m.answered}/${m.total} answered, ${m.skipped} skipped)`);
    $('next').disabled=false;$('skip').disabled=false;await initMic();}
  else if(m.type==='question'){
    log(`Q${m.sequence_no} [${m.category}] ${m.text}`,'q');
    $('rec').disabled=false;}
  else if(m.type==='recorded'){
    log(`answer recorded — ${m.bytes.toLocaleString()} bytes (${m.mime_type})`,'a');
    log(`progress ${m.answered}/${m.total}`);$('rec').disabled=true;}
  else if(m.type==='skipped'){log(`skipped Q${m.sequence_no}`);$('rec').disabled=true;}
  else if(m.type==='complete'){log(`✓ complete — ${m.answered}/${m.total} answered`,'a');}
  else if(m.type==='error'){log('error: '+m.detail,'e');}
}
async function initMic(){
  if(rec)return;
  try{const s=await navigator.mediaDevices.getUserMedia({audio:true});
    rec=new MediaRecorder(s);
    rec.ondataavailable=e=>chunks.push(e.data);
    rec.onstop=async()=>{const blob=new Blob(chunks,{type:rec.mimeType});chunks=[];
      const b64=btoa(String.fromCharCode(...new Uint8Array(await blob.arrayBuffer())));
      log(`sending ${blob.size.toLocaleString()} bytes of audio…`);
      send({type:'answer',audio_b64:b64,mime_type:rec.mimeType.split(';')[0]});};
    log('microphone ready');
  }catch(e){log('microphone unavailable: '+e.message,'e');}
}
function toggleRec(){
  if(!rec)return;
  if(!recording){chunks=[];rec.start();recording=true;$('rec').textContent='Stop & send';}
  else{rec.stop();recording=false;$('rec').textContent='Hold to answer';}
}
</script>
"""


@router.get("/voice/demo", response_class=HTMLResponse, include_in_schema=False)
def voice_demo_page():
    """
    A self-contained browser client for demonstrating the voice interview with a
    real microphone. Served from the API so it is same-origin and needs no CORS
    exception. Open http://localhost:8000/api/interviews/voice/demo
    """
    return HTMLResponse(_DEMO_PAGE)


@router.websocket("/voice/{interview_id}")
async def voice_interview(
    websocket: WebSocket,
    interview_id: int,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    await websocket.accept()

    user = _authenticate(token, db)
    if user is None:
        await websocket.send_json({"type": "error", "detail": "Invalid or missing token."})
        await websocket.close(code=4401)
        return

    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id, Interview.user_id == user.id)
        .first()
    )
    if interview is None:
        await websocket.send_json({"type": "error", "detail": "Interview not found."})
        await websocket.close(code=4404)
        return

    progress = _progress(db, interview.id)
    if progress["total"] == 0:
        await websocket.send_json({"type": "error", "detail": "This interview has no questions."})
        await websocket.close(code=4409)
        return

    # Connecting is starting: a candidate on the line is a session in progress.
    if interview.status in (SessionStatus.CREATED, SessionStatus.ABANDONED):
        interview.status = SessionStatus.IN_PROGRESS
        interview.started_at = interview.started_at or datetime.now(timezone.utc)
        db.commit()

    # Connecting here bypasses POST /interviews/start, which is where the clock
    # is normally snapshotted. Without this an interview begun straight from the
    # socket would have no countdown at all — so set it the same way, once, and
    # never overwrite a value an earlier start already fixed.
    if interview.question_seconds is None:
        interview.question_seconds = per_question_seconds(
            get_settings(db).session_minutes,
            progress["total"],
            difficulty=interview.difficulty.value,
            interview_type=interview.interview_type.value,
        )
        db.commit()

    await websocket.send_json(
        {
            "type": "ready",
            "interview_id": interview.id,
            "interview_type": interview.interview_type.value,
            "domain": interview.domain,
            "difficulty": interview.difficulty.value,
            "status": interview.status.value,
            "paused": interview.status == SessionStatus.PAUSED,
            "total_paused_seconds": interview.total_paused_seconds or 0,
            # Module 4: seconds per question, fixed when the session started.
            # Null means this interview predates the timer — the client shows
            # no countdown rather than inventing a limit.
            "question_seconds": interview.question_seconds,
            "analysis_enabled": settings.ANALYSE_ANSWERS,
            **progress,
        }
    )

    current: Optional[InterviewQuestion] = None

    # Analyses still running in the background. Held so the interview can be
    # settled against them: they commit through their own sessions, and a score
    # computed while one is still in flight would silently omit that answer.
    pending: set[asyncio.Task] = set()

    async def settle_analyses() -> None:
        """
        Wait for every in-flight analysis, then re-read what they wrote.

        Called before anything that scores the interview. `expire_all` matters
        as much as the wait: the background tasks commit through their own
        sessions, so without it this session would score from the stale
        question rows it already has in memory and lose exactly the answers it
        just waited for.
        """
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        db.expire_all()

    async def serve_next() -> tuple[Optional[InterviewQuestion], bool]:
        """
        Send the next unhandled question, or close the interview out.

        Returns (question, finished). Shared by `next` and `skip` so that
        passing on a question moves straight to the following one rather than
        making the candidate ask for it separately.
        """
        question = _next_question(db, interview.id)

        if question is None:
            # The last answer's analysis may still be running; scoring now
            # would leave it out of the result the candidate is about to see.
            await settle_analyses()
            interview.status = SessionStatus.COMPLETED
            interview.completed_at = datetime.now(timezone.utc)
            interview.duration_seconds = finalise_duration(interview)
            score = _score_interview(db, interview)
            db.commit()
            await websocket.send_json(
                {
                    "type": "complete",
                    "interview_id": interview.id,
                    "score": score,
                    **_progress(db, interview.id),
                }
            )
            return None, True

        question.asked_at = datetime.now(timezone.utc)
        db.commit()
        await websocket.send_json(
            {
                "type": "question",
                "sequence_no": question.sequence_no,
                "category": question.category,
                "text": question.question_text,
            }
        )
        return question, False

    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("type")

            # A paused interview accepts only the actions that get it out of
            # being paused. Serving the next question while paused would defeat
            # the point — the candidate could read ahead on a stopped clock.
            if interview.status == SessionStatus.PAUSED and action in ("next", "answer", "skip"):
                await websocket.send_json(
                    {
                        "type": "error",
                        "detail": "This interview is paused. Resume it to carry on.",
                    }
                )
                continue

            # ---------------------------------------------------- next question
            if action == "next":
                current, finished = await serve_next()
                if finished:
                    break

            # ------------------------------------------------- spoken answer
            elif action == "answer":
                if current is None:
                    await websocket.send_json(
                        {"type": "error", "detail": "Ask for a question first."}
                    )
                    continue

                b64 = message.get("audio_b64") or ""
                if not b64:
                    await websocket.send_json({"type": "error", "detail": "No audio received."})
                    continue
                if len(b64) > _max_b64_chars():
                    await websocket.send_json(
                        {
                            "type": "error",
                            "detail": (
                                f"Answer audio exceeds the "
                                f"{settings.MAX_ANSWER_AUDIO_MB} MB limit."
                            ),
                        }
                    )
                    continue

                try:
                    audio_bytes = base64.b64decode(b64, validate=True)
                except (binascii.Error, ValueError):
                    await websocket.send_json({"type": "error", "detail": "Audio is not valid base64."})
                    continue

                if not audio_bytes:
                    await websocket.send_json(
                        {"type": "error", "detail": "The recording was empty. Please answer again."}
                    )
                    continue

                try:
                    path, mime = _store_answer_audio(
                        audio_bytes,
                        message.get("mime_type", "audio/webm"),
                        interview.id,
                    )
                except OSError:
                    logger.exception("Could not store answer audio for question %s", current.id)
                    await websocket.send_json(
                        {"type": "error", "detail": "The recording could not be saved."}
                    )
                    continue

                current.answer_audio_path = path
                current.answer_audio_mime = mime
                current.answer_duration_seconds = _duration(message.get("duration_seconds"))
                current.answered_at = datetime.now(timezone.utc)
                db.commit()

                # Acknowledge the recording before analysing it. Transcription
                # takes seconds; making the candidate stare at a dead screen
                # until it finishes would be worse than telling them their
                # answer is safely stored and following up.
                await websocket.send_json(
                    {
                        "type": "recorded",
                        "sequence_no": current.sequence_no,
                        "bytes": len(audio_bytes),
                        "mime_type": mime,
                        "duration_seconds": current.answer_duration_seconds,
                        "analysis_pending": settings.ANALYSE_ANSWERS,
                        **_progress(db, interview.id),
                    }
                )

                if settings.ANALYSE_ANSWERS:
                    # Deliberately not awaited: the loop has to get back to
                    # receive_json so `next`, `skip` and `end` stay responsive
                    # while this runs. Tracked in `pending` so the interview is
                    # never scored or closed out with an analysis still in
                    # flight.
                    task = asyncio.create_task(
                        _analyse_answer(
                            websocket, interview.id, current.id, audio_bytes, mime
                        )
                    )
                    pending.add(task)
                    task.add_done_callback(pending.discard)

                current = None

            # -------------------------------------------------------- skip
            elif action == "skip":
                if current is None:
                    await websocket.send_json({"type": "error", "detail": "Nothing to skip."})
                    continue

                # Recorded as not attempted, not as an empty answer: skipped_at
                # is set and answered_at is deliberately left alone.
                skipped_no = current.sequence_no
                current.skipped_at = datetime.now(timezone.utc)
                db.commit()

                await websocket.send_json(
                    {
                        "type": "skipped",
                        "sequence_no": skipped_no,
                        "attempted": False,
                        **_progress(db, interview.id),
                    }
                )

                # Skipping moves the interview on by itself — the candidate
                # should not have to ask for the next question separately.
                current, finished = await serve_next()
                if finished:
                    break

            # ------------------------------------------------ pause / resume
            elif action == "pause":
                if interview.status != SessionStatus.IN_PROGRESS:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "detail": f"Cannot pause an interview that is {interview.status.value}.",
                        }
                    )
                    continue

                interview.status = SessionStatus.PAUSED
                interview.paused_at = datetime.now(timezone.utc)
                db.commit()
                await websocket.send_json(
                    {
                        "type": "paused",
                        "interview_id": interview.id,
                        "total_paused_seconds": interview.total_paused_seconds or 0,
                    }
                )

            elif action == "resume":
                if interview.status != SessionStatus.PAUSED:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "detail": f"This interview is not paused (it is {interview.status.value}).",
                        }
                    )
                    continue

                if interview.paused_at is not None:
                    paused_for = (
                        datetime.now(timezone.utc) - interview.paused_at
                    ).total_seconds()
                    interview.total_paused_seconds = int(
                        (interview.total_paused_seconds or 0) + max(paused_for, 0)
                    )

                interview.status = SessionStatus.IN_PROGRESS
                interview.paused_at = None
                db.commit()
                await websocket.send_json(
                    {
                        "type": "resumed",
                        "interview_id": interview.id,
                        "total_paused_seconds": interview.total_paused_seconds,
                    }
                )

            # -------------------------------------------------------- close
            elif action == "end":
                # Ending is a decision, so it has to leave a terminal state
                # behind. Previously this closed the socket and left the
                # interview IN_PROGRESS for ever, which meant a candidate who
                # stopped early stayed "in progress" in every list and count.
                #
                # Unanswered questions are left untouched: not skipped, not
                # back-filled. "Ran out of time" and "passed on it" are
                # different facts and ending must not merge them.
                if interview.status == SessionStatus.PAUSED and interview.paused_at is not None:
                    paused_for = (
                        datetime.now(timezone.utc) - interview.paused_at
                    ).total_seconds()
                    interview.total_paused_seconds = int(
                        (interview.total_paused_seconds or 0) + max(paused_for, 0)
                    )

                await settle_analyses()

                score = {"available": interview.overall_score is not None}
                if score["available"]:
                    score = {
                        "available": True,
                        "overall": interview.overall_score,
                        "rating": scoring.rating_label(interview.overall_score),
                    }

                if interview.status != SessionStatus.COMPLETED:
                    interview.status = SessionStatus.COMPLETED
                    interview.completed_at = datetime.now(timezone.utc)
                    interview.paused_at = None
                    interview.duration_seconds = finalise_duration(interview)
                    score = _score_interview(db, interview)
                    db.commit()

                await websocket.send_json(
                    {
                        "type": "closed",
                        "interview_id": interview.id,
                        "status": interview.status.value,
                        "score": score,
                        **_progress(db, interview.id),
                    }
                )
                break

            else:
                await websocket.send_json(
                    {"type": "error", "detail": f"Unknown action: {action!r}"}
                )

    except WebSocketDisconnect:
        # Candidate dropped mid-interview. Leave it IN_PROGRESS so they can
        # reconnect and carry on from the next unanswered question.
        logger.info("Voice interview %s disconnected by client.", interview.id)
        return
    except Exception:
        logger.exception("Voice interview %s failed.", interview.id)
        await _try_send(websocket, {"type": "error", "detail": "Internal error."})
    finally:
        # Let the background analyses finish rather than cancelling them on the
        # way out. They write the transcript and score straight to the
        # database, and the report is fetched over HTTP after this socket is
        # gone — so a candidate who closes the tab the moment they finish still
        # gets the analysis of the answers they gave. Their frames are dropped
        # harmlessly by _try_send once the socket has closed.
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    try:
        await websocket.close()
    except Exception:
        pass
