import React, { useState } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { Panel } from './Panel';

/**
 * Module 10 — two to four candidates on the same rubric axes.
 *
 * Three constraints here are binding decisions, not styling choices, and none
 * of them may be relaxed without reopening the gate that set them:
 *
 *   **Nothing sorts.** Candidates appear in the order the recruiter picked
 *   them. There is no column header to click, no sort control, and the server
 *   exposes no sort parameter. Ordering four people by a number an AI produced
 *   is the act this module refuses to perform on a recruiter's behalf —
 *   ranking exists once, on the leaderboard, where it is labelled as ranking.
 *
 *   **Two to four.** One is not a comparison. Five makes the axes unreadable.
 *   Enforced server-side too, so this is a courtesy rather than the guard.
 *
 *   **Thin evidence stays visibly thin.** Every cell carries how many graded
 *   answers stand behind it. On a candidate's own dashboard that is a
 *   courtesy; side by side against another person it is a fairness
 *   requirement, because a figure from one answer must never read as
 *   equivalent to one from twelve.
 */

const AXIS_LABEL = {
  communication: 'Communication',
  confidence: 'Confidence',
  technical_relevance: 'Technical',
  professionalism: 'Professionalism',
};

const MIN = 2;
const MAX = 4;

export default function CandidateCompare() {
  const candidates = useApi(() => api.recruiterCandidates({ limit: 100 }));
  const [picked, setPicked] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const toggle = (id) =>
    setPicked((current) =>
      current.includes(id)
        ? current.filter((x) => x !== id)
        : current.length >= MAX
          ? current
          : [...current, id],
    );

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.compareCandidates(picked));
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>Compare candidates</h2>
      <p className="muted">
        Pick {MIN}–{MAX} candidates. They are shown in the order you select them and cannot be
        sorted by score — this view is for reading side by side, not for ranking people.
      </p>

      <Panel {...candidates} onRetry={candidates.reload}>
        <div className="tags gap-top">
          {candidates.data?.map((row) => {
            const on = picked.includes(row.user_id);
            const full = !on && picked.length >= MAX;
            return (
              <button
                type="button"
                key={row.user_id}
                className={`badge ${on ? 'badge-ok' : 'badge-muted'}`}
                style={{
                  cursor: full ? 'not-allowed' : 'pointer',
                  opacity: full ? 0.45 : 1,
                  border: 'none',
                }}
                disabled={full}
                aria-pressed={on}
                onClick={() => toggle(row.user_id)}
              >
                {on ? `${picked.indexOf(row.user_id) + 1}. ` : ''}
                {row.name}
              </button>
            );
          })}
        </div>
      </Panel>

      <div className="actions gap-top">
        <button
          className="btn btn-primary"
          disabled={busy || picked.length < MIN || picked.length > MAX}
          onClick={run}
        >
          {busy ? 'Comparing…' : `Compare ${picked.length || ''}`}
        </button>
        {picked.length > 0 && (
          <button className="btn" onClick={() => { setPicked([]); setResult(null); }}>
            Clear
          </button>
        )}
      </div>

      {picked.length === 1 && (
        <small className="muted">
          Pick at least one more — a single candidate is not a comparison.
        </small>
      )}
      {picked.length >= MAX && (
        <small className="muted">
          Four is the maximum; beyond that the axes stop being readable.
        </small>
      )}
      {error && <p className="error">{error}</p>}

      {result && (
        <div className="gap-top" style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {/* Plain text, deliberately not buttons: a clickable column
                    header is the affordance that turns this into a ranking. */}
                <th style={{ textAlign: 'left', padding: '8px 12px' }}>
                  <span className="label">Axis</span>
                </th>
                {result.candidates.map((c, i) => (
                  <th key={c.user_id} style={{ textAlign: 'left', padding: '8px 12px' }}>
                    <strong>
                      {i + 1}. {c.name}
                    </strong>
                    <small className="muted" style={{ display: 'block' }}>
                      {c.interviews_scored} scored interview
                      {c.interviews_scored === 1 ? '' : 's'}
                    </small>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.axes.map((axis, row) => (
                <tr key={axis} style={{ borderTop: '1px solid var(--line)' }}>
                  <td style={{ padding: '10px 12px' }}>
                    <strong>{AXIS_LABEL[axis] ?? axis}</strong>
                  </td>
                  {result.candidates.map((c) => {
                    const cell = c.cells[row];
                    return (
                      <td key={c.user_id} style={{ padding: '10px 12px' }}>
                        <strong>{cell.score ?? '—'}</strong>
                        <small
                          className="muted"
                          style={{ display: 'block' }}
                          title={
                            cell.provisional
                              ? 'Too few graded answers to compare against a candidate with more'
                              : undefined
                          }
                        >
                          {cell.answers_graded} answer{cell.answers_graded === 1 ? '' : 's'}
                          {cell.provisional ? ' · provisional' : ''}
                        </small>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>

          <p className="note gap-top">{result.note}</p>
        </div>
      )}
    </div>
  );
}
