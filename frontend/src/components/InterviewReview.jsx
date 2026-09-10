import React, { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { AnswerDetail } from './AnalysisReport';
import Module7Report from './Module7Report';
import BehaviorReport from './BehaviorReport';
import { RATING_TONE } from '../lib/scoring';

const AXES = [
  ['communication', 'Communication'],
  ['confidence', 'Confidence'],
  ['technical_relevance', 'Technical relevance'],
  ['professionalism', 'Professionalism'],
];

/**
 * One answer's recording, fetched only once the candidate asks for it — an
 * eager fetch per question would mean N blob downloads on every open.
 */
function AnswerAudio({ interviewId, sequenceNo }) {
  const [state, setState] = useState('idle'); // idle | loading | ready | error
  const [url, setUrl] = useState(null);

  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  if (state === 'ready') return <audio controls src={url} style={{ width: '100%' }} />;

  return (
    <button
      type="button"
      className="btn"
      disabled={state === 'loading'}
      onClick={async () => {
        setState('loading');
        try {
          setUrl(await api.answerAudioUrl(interviewId, sequenceNo));
          setState('ready');
        } catch {
          setState('error');
        }
      }}
    >
      {state === 'loading' ? 'Loading…' : state === 'error' ? 'Unavailable' : 'Play answer'}
    </button>
  );
}

/**
 * Module 9: the same report as a PDF.
 *
 * Its own component so the download's in-flight and failed states live beside
 * the button rather than in the modal's state — a failed export must not read
 * as the whole review having failed.
 */
function DownloadReport({ interviewId }) {
  const [state, setState] = useState('idle'); // idle | working | error

  return (
    <>
      <button
        type="button"
        className="btn"
        disabled={state === 'working'}
        onClick={async () => {
          setState('working');
          try {
            await api.downloadInterviewReport(interviewId);
            setState('idle');
          } catch {
            setState('error');
          }
        }}
      >
        {state === 'working' ? 'Preparing…' : 'Download PDF'}
      </button>
      {state === 'error' && (
        <small className="error">The report could not be generated.</small>
      )}
    </>
  );
}

/**
 * A past interview in full: the session recording, and every question with
 * its transcript, its own recording and its Module 5 score.
 *
 * Two independent fetches — GET .../analysis for the per-question detail
 * (transcripts, scores) and GET .../recording for the camera video — because
 * either can be legitimately absent (analysis disabled, camera never turned
 * on) without the other being affected.
 */
export default function InterviewReview({ interview, onClose }) {
  const analysis = useApi(() => api.interviewAnalysis(interview.id), [interview.id]);
  const [video, setVideo] = useState({ state: 'loading', url: null });

  useEffect(() => {
    let cancelled = false;
    let objectUrl = null;

    api
      .recordingUrl(interview.id)
      .then((url) => {
        objectUrl = url;
        if (cancelled) URL.revokeObjectURL(url);
        else setVideo({ state: 'ready', url });
      })
      .catch(() => {
        if (!cancelled) setVideo({ state: 'none', url: null });
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [interview.id]);

  const score = analysis.data?.summary?.score;

  return (
    <div
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-label={`Interview ${interview.id} review`}
    >
      <div className="modal-box modal-box-wide">
        <h2>
          {interview.interview_type} &middot; {interview.domain}
        </h2>
        <p className="muted">
          {interview.difficulty.toLowerCase()} &middot; {interview.question_count} question
          {interview.question_count === 1 ? '' : 's'} &middot;{' '}
          {interview.status.toLowerCase().replace('_', ' ')}
        </p>

        <div className="row">
          <div>
            <strong>Overall score</strong>
            <small>
              Communication 30% &middot; Confidence 25% &middot; Technical relevance 30% &middot;
              Professionalism 15%. An AI assessment against this fixed rubric, not a certified
              evaluation.
            </small>
          </div>
          {score?.available ? (
            <span className={`badge ${RATING_TONE[score.rating] ?? 'badge-muted'}`}>
              {score.overall.toFixed(1)} &middot; {score.rating}
            </span>
          ) : (
            <span className="badge badge-muted">not scored</span>
          )}
        </div>

        <Module7Report summary={analysis.data?.summary} behavior={analysis.data?.behavior} />

        <BehaviorReport behavior={analysis.data?.behavior} />

        <p className="label gap-top">Camera recording</p>
        {video.state === 'loading' && <p className="note">Loading…</p>}
        {video.state === 'ready' && (
          <video controls src={video.url} style={{ width: '100%', borderRadius: 8 }} />
        )}
        {video.state === 'none' && (
          <p className="muted">No camera recording was kept for this interview.</p>
        )}

        <p className="label gap-top">Questions</p>
        {analysis.loading && <p className="note">Loading…</p>}
        {analysis.error && <p className="error">This interview's analysis could not be loaded.</p>}

        {analysis.data?.questions.map((q) => {
          const qScore = q.analysis?.score;
          return (
            <div key={q.sequence_no} className="card gap-top">
              <h3>
                Q{q.sequence_no} &middot; {q.category}
              </h3>
              <p className="quote">{q.question_text}</p>

              {q.transcript && (
                <div className="gap-top">
                  <AnswerAudio interviewId={interview.id} sequenceNo={q.sequence_no} />
                </div>
              )}

              {/* The same six Module 5 sections the candidate saw at the end of
                  the interview, so history and the live report cannot drift. */}
              <AnswerDetail analysis={q.analysis} transcript={q.transcript} />

              {qScore?.available ? (
                <div className="gap-top">
                  {AXES.map(([key, label]) => (
                    <div key={key} className="row">
                      <div>
                        <strong>{label}</strong>
                        <small>{qScore[key]}/100</small>
                      </div>
                      <div className="meter">
                        <i style={{ width: `${qScore[key]}%` }} />
                      </div>
                    </div>
                  ))}
                  <p className="muted gap-top">{qScore.rationale}</p>
                </div>
              ) : (
                q.transcript && (
                  <p className="muted gap-top">
                    {qScore?.reason ?? 'This answer was not scored.'}
                  </p>
                )
              )}
            </div>
          );
        })}

        <div className="actions gap-top">
          <button className="btn btn-primary" onClick={onClose}>
            Close
          </button>
          <DownloadReport interviewId={interview.id} />
        </div>
      </div>
    </div>
  );
}
