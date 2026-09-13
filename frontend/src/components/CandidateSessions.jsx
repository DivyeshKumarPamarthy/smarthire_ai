import React from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { Panel } from './Panel';
import RecruiterCandidatePerformance from './RecruiterCandidatePerformance';
import { RATING_TONE } from '../lib/scoring';

const shortTime = (iso) => (iso ? new Date(iso).toLocaleString() : '—');

const duration = (seconds) =>
  seconds === null || seconds === undefined
    ? '—'
    : seconds < 60
      ? '<1m'
      : `${Math.round(seconds / 60)}m`;

/**
 * One candidate's completed interviews, for a recruiter.
 *
 * Shows the Module 5 score and the Module 6 attention figures side by side,
 * including the confidence percentage. Named emotion readings are filtered out
 * on the server: a percentage carries its uncertainty visibly, a word like
 * "nervous" beside someone's name does not.
 *
 * Presented as context rather than as a verdict, and the wording works to keep
 * it that way: low eye contact is reported as a number, never as a judgement.
 * Eye-contact norms differ by culture and by neurodivergence.
 */
export default function CandidateSessions({ candidate, onClose }) {
  const sessions = useApi(() => api.candidateInterviews(candidate.user_id), [candidate.user_id]);
  // Module 10. Its own request: this walks every answer the candidate has
  // given, and the session list should not wait on that scan.
  const performance = useApi(
    () => api.recruiterCandidatePerformance(candidate.user_id),
    [candidate.user_id],
  );

  return (
    <div
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-label={`${candidate.name} sessions`}
    >
      <div className="modal-box modal-box-wide">
        <h2>{candidate.name}</h2>
        <p className="muted">{candidate.email}</p>

        <RecruiterCandidatePerformance {...performance} />

        <Panel
          {...sessions}
          isEmpty={sessions.data?.length === 0}
          empty="This candidate has not completed an interview yet."
          onRetry={sessions.reload}
        >
          <div className="scroll-x gap-top">
            <table className="table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Domain</th>
                  <th>Completed</th>
                  <th className="num">Duration</th>
                  <th className="num">Score</th>
                  <th className="num">Confidence</th>
                  <th className="num">Eye contact</th>
                  <th className="num">Look-aways</th>
                  <th>Attention</th>
                </tr>
              </thead>
              <tbody>
                {sessions.data?.map((row) => {
                  const a = row.attention;
                  return (
                    <tr key={row.interview_id}>
                      <td>{row.interview_type}</td>
                      <td>{row.domain}</td>
                      <td className="num">{shortTime(row.completed_at)}</td>
                      <td className="num">{duration(row.duration_seconds)}</td>
                      <td className="num">
                        {row.overall_score != null ? (
                          <span className={`badge ${RATING_TONE[row.score_rating] ?? 'badge-muted'}`}>
                            {row.overall_score.toFixed(1)} &middot; {row.score_rating}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="num">
                        {a?.available && a.confidence_percent != null ? (
                          `${a.confidence_percent}%`
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="num">
                        {a?.available ? `${a.eye_contact_percent}%` : <span className="muted">—</span>}
                      </td>
                      <td className="num">
                        {a?.available ? a.look_aways : <span className="muted">—</span>}
                      </td>
                      <td>
                        {a?.available ? (
                          <span className="badge badge-muted">{a.engagement}</span>
                        ) : (
                          <span className="muted">no camera</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* The disclosure is deliberately not collapsible and not a tooltip.
            A recruiter is making decisions about a person from these numbers
            and has to see what they are worth while reading them. */}
        <p className="note gap-top">
          These figures are uncalibrated estimates measured by the candidate&apos;s own browser,
          and are submitted by it — treat them as context, never as evidence. Eye-contact norms
          differ by culture and by neurodivergence: less eye contact is not worse interviewing.
          <strong> Confidence</strong> estimates how composed the candidate&apos;s face looked, not
          how confident they were: a calm face scores high whether or not the person felt calm, and
          an animated one scores lower without anything being wrong. Named emotion readings are not
          shown here, because a label beside someone&apos;s name outlives its caveat. None of this
          affects the score or the leaderboard.
        </p>

        <div className="actions gap-top">
          <button className="btn btn-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
