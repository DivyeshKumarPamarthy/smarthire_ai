import React, { useState } from 'react';
import { RATING_TONE } from '../lib/scoring';
import { api } from '../lib/api';

/**
 * Module 8 — the candidate's history rolled up: skills, trend, weak areas.
 *
 * Three things this screen is careful about, because all three are ways a
 * dashboard can quietly lie:
 *
 *   A category with one graded answer is drawn differently from one with ten,
 *   and says so. Averaging a single answer produces a number that looks
 *   exactly as authoritative as a well-evidenced one.
 *
 *   The trend line only claims a direction once there are enough interviews to
 *   compare halves. Below that it plots the points and says nothing about
 *   where they are heading.
 *
 *   "Weak areas" is worded as what the record shows, never as a prediction.
 *   The backend computes it from answers already given, and the copy here has
 *   to match that or it overclaims on the data's behalf.
 */

const AXIS_LABEL = {
  communication: 'Communication',
  confidence: 'Confidence',
  technical_relevance: 'Technical',
  professionalism: 'Professionalism',
};

const DIRECTION = {
  improving: { label: 'Improving', tone: 'badge-ok' },
  declining: { label: 'Declining', tone: 'badge-bad' },
  steady: { label: 'Steady', tone: 'badge-muted' },
  insufficient_data: { label: 'Not enough data', tone: 'badge-muted' },
};

/** Score 0-100 to a bar width, guarded against a missing figure. */
const pct = (value) => `${Math.max(0, Math.min(100, value ?? 0))}%`;

/**
 * The trend as a plain SVG line. No chart library: this is one series of at
 * most a few dozen points, and pulling in a charting package to draw it would
 * cost more than the feature.
 */
function TrendChart({ points, reference = null, referenceLabel = '' }) {
  if (points.length < 2) return null;

  const W = 640;
  const H = 120;
  const PAD = 8;
  const scores = points.map((p) => p.score);
  const lo = Math.min(...scores, 0);
  const hi = Math.max(...scores, 100);
  const span = hi - lo || 1;
  const refY =
    reference === null || reference === undefined
      ? null
      : H - PAD - ((reference - lo) / span) * (H - 2 * PAD);

  const xy = points.map((p, i) => [
    PAD + (i * (W - 2 * PAD)) / Math.max(points.length - 1, 1),
    H - PAD - ((p.score - lo) / span) * (H - 2 * PAD),
  ]);
  const line = xy.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${line} L${xy[xy.length - 1][0].toFixed(1)},${H - PAD} L${xy[0][0].toFixed(1)},${H - PAD} Z`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`Score across ${points.length} interviews, from ${points[0].score} to ${points[points.length - 1].score}`}
      style={{ width: '100%', height: 'auto', display: 'block', marginTop: 12 }}
    >
      <path d={area} fill="var(--blue)" opacity="0.12" />
      {/* The all-time average, drawn so the candidate can see that the low
          lifetime figure and the high recent point describe the same axis over
          different windows — rather than reading them as a contradiction. */}
      {refY !== null && (
        <>
          <line
            x1={PAD} y1={refY} x2={W - PAD} y2={refY}
            stroke="var(--tx-2)" strokeWidth="1" strokeDasharray="4 4"
          />
          <text
            x={W - PAD} y={refY - 5} textAnchor="end"
            fill="var(--tx-2)" fontSize="11" fontFamily="var(--mono)"
          >
            {referenceLabel}
          </text>
        </>
      )}
      <path d={line} fill="none" stroke="var(--blue)" strokeWidth="2" strokeLinejoin="round" />
      {xy.map(([x, y], i) => (
        <circle
          key={points[i].interview_id}
          cx={x}
          cy={y}
          r={i === xy.length - 1 ? 4 : 2.5}
          fill={i === xy.length - 1 ? 'var(--blue)' : 'var(--bg)'}
          stroke="var(--blue)"
          strokeWidth="1.5"
        />
      ))}
    </svg>
  );
}

/**
 * Module 10, Slice 2 — the whole history as one PDF.
 *
 * Its own component so a failed export reads as a failed export, rather than
 * making the whole performance card look broken.
 */
function DownloadHistory() {
  const [state, setState] = useState('idle'); // idle | working | error

  return (
    <div className="actions gap-top">
      <button
        type="button"
        className="btn"
        disabled={state === 'working'}
        onClick={async () => {
          setState('working');
          try {
            await api.downloadHistoryReport();
            setState('idle');
          } catch {
            setState('error');
          }
        }}
      >
        {state === 'working' ? 'Preparing…' : 'Download full history (PDF)'}
      </button>
      {state === 'error' && (
        <small className="error">The report could not be generated.</small>
      )}
    </div>
  );
}

export default function PerformanceAnalytics({ data, loading, error }) {
  if (loading) return <p className="note">Loading your performance history…</p>;
  if (error) return <p className="error">Your performance history could not be loaded.</p>;
  if (!data) return null;

  const { skills = [], trend, weak_areas: weak, axis_progress: progress } = data;
  const direction = DIRECTION[trend?.direction] ?? DIRECTION.insufficient_data;
  const hasScores = (trend?.interviews_scored ?? 0) > 0;

  if (!hasScores) {
    return (
      <>
        <p className="note">
          No interview of yours has been scored yet. Finish an interview to start building a
          history here — skills, trend and weak areas all read from your scored answers.
        </p>
        <DownloadHistory />
      </>
    );
  }

  return (
    <>
      {/* ---------------- trend ---------------- */}
      <p className="label">Performance trend</p>
      <div className="row">
        <div>
          <strong>
            {trend.interviews_scored} scored interview{trend.interviews_scored === 1 ? '' : 's'}
          </strong>
          <small>
            average {trend.average} · best {trend.best}
            {trend.change !== null && trend.change !== undefined
              ? ` · ${trend.change > 0 ? '+' : ''}${trend.change} between your earlier and later halves`
              : ''}
          </small>
        </div>
        <span className={`badge ${direction.tone}`}>{direction.label}</span>
      </div>

      <TrendChart points={trend.points} />

      {trend.direction === 'insufficient_data' && (
        <small className="muted">
          A direction needs at least four scored interviews to compare against — until then these
          are just your scores, not a trajectory.
        </small>
      )}

      {/* ---------------- improvement on the named weak axis ---------------- */}
      {progress?.available && (
        <>
          <p className="label gap-top">
            Progress on {AXIS_LABEL[progress.axis] ?? progress.axis}
          </p>
          <small className="muted">
            The axis you were told to work on, tracked across your interviews. This is
            deliberately not your overall score — that can rise while the thing you were asked
            to fix stays exactly where it was.
          </small>
          <small className="muted">
            Each point is <strong>one finished interview&apos;s average</strong> on this axis.
            That is a different window from the {weak?.weakest_axis_score} below, which averages
            every graded answer you have ever given on it — including answers from interviews
            you started and did not finish. The two differ for that reason, not because either
            is wrong.
          </small>
          <div className="row">
            <div>
              <strong>
                {progress.first} → {progress.latest}
              </strong>
              <small>
                across {progress.interviews} interview{progress.interviews === 1 ? '' : 's'}
                {progress.change !== null && progress.change !== undefined
                  ? ` · ${progress.change > 0 ? '+' : ''}${progress.change} between your earlier and later halves`
                  : ''}
              </small>
            </div>
            <span className={`badge ${DIRECTION[progress.direction]?.tone ?? 'badge-muted'}`}>
              {DIRECTION[progress.direction]?.label ?? progress.direction}
            </span>
          </div>

          <TrendChart
            points={progress.points}
            reference={weak?.available ? weak.weakest_axis_score : null}
            referenceLabel={`all-time ${weak?.weakest_axis_score ?? ''}`}
          />

          {progress.direction === 'insufficient_data' && (
            <small className="muted">
              Whether this is moving needs at least four scored interviews to compare against —
              the same bar your overall trend uses. Until then these are just your scores on
              that axis.
            </small>
          )}
        </>
      )}
      {progress && !progress.available && (
        <>
          <p className="label gap-top">
            Progress on {AXIS_LABEL[progress.axis] ?? progress.axis}
          </p>
          <p className="note">{progress.reason}</p>
        </>
      )}

      {/* ---------------- skills ---------------- */}
      <p className="label gap-top">Skill-wise breakdown</p>
      {skills.length === 0 ? (
        <p className="note">No answer has been graded by category yet.</p>
      ) : (
        <>
          <small className="muted">
            Weakest first, by question category. Each bar is the average across every graded
            answer you have given in that category.
          </small>
          {skills.map((skill) => (
            <div className="row" key={skill.category}>
              <div>
                <strong>
                  {skill.category}
                  {skill.provisional && (
                    <span className="badge badge-muted" style={{ marginLeft: 8 }}>
                      {skill.answers_graded} answer{skill.answers_graded === 1 ? '' : 's'}
                    </span>
                  )}
                </strong>
                <small>
                  {Object.entries(skill.axes)
                    .map(([axis, value]) => `${AXIS_LABEL[axis] ?? axis} ${value}`)
                    .join(' · ')}
                </small>
              </div>
              <div style={{ minWidth: 160 }}>
                <strong>{skill.overall}</strong>
                <div className="meter">
                  <i style={{ width: pct(skill.overall) }} />
                </div>
              </div>
            </div>
          ))}
          {skills.some((s) => s.provisional) && (
            <small className="muted">
              A category tagged with an answer count has fewer than three graded answers behind
              it. It is shown because it is your real data, but it is too thin to compare against
              the others.
            </small>
          )}
        </>
      )}

      {/* ---------------- weak areas ---------------- */}
      <p className="label gap-top">Where you are weakest</p>
      {!weak?.available ? (
        <p className="note">{weak?.reason ?? 'Nothing has been scored yet.'}</p>
      ) : (
        <>
          <div className="row">
            <div>
              <strong>{AXIS_LABEL[weak.weakest_axis] ?? weak.weakest_axis}</strong>
              <small>
                Your lowest rubric axis, averaging {weak.weakest_axis_score} across{' '}
                {weak.graded_answers} graded answer{weak.graded_answers === 1 ? '' : 's'} —
                every answer you have given on it, including ones from interviews you did not
                finish. The chart above plots finished interviews only, which is why its recent
                points sit higher.
              </small>
            </div>
            <span className="badge badge-warn">{weak.weakest_axis_score}</span>
          </div>

          {weak.weakest_category ? (
            <div className="row">
              <div>
                <strong>{weak.weakest_category}</strong>
                <small>Your lowest-scoring question category with enough answers to judge.</small>
              </div>
              <span className="badge badge-warn">{weak.weakest_category_score}</span>
            </div>
          ) : (
            /* Not an error, and not nothing: no category yet has the three
               graded answers this platform requires before naming one as a
               weakness. Saying so beats the row silently disappearing — the
               same rule the per-answer report follows for a section it could
               not produce. */
            <p className="note">
              No single question category has enough finished answers yet to name as your
              weakest — that needs at least three in the same category. Your weakest rubric
              axis above is based on all {weak.graded_answers} of them together.
            </p>
          )}

          <div className="tags gap-top">
            {Object.entries(weak.axis_averages).map(([axis, value]) => (
              <span
                className={`badge ${axis === weak.weakest_axis ? 'badge-warn' : 'badge-muted'}`}
                key={axis}
              >
                {AXIS_LABEL[axis] ?? axis} {value}
              </span>
            ))}
          </div>

          {weak.practice_recommendations?.length > 0 && (
            <>
              <small className="muted gap-top">Practice next:</small>
              {weak.practice_recommendations.map((item) => (
                <p className="note" key={item}>
                  {item}
                </p>
              ))}
            </>
          )}

          {weak.learning_resources?.length > 0 && (
            <>
              <small className="muted">Where to practise:</small>
              <div className="tags">
                {weak.learning_resources.map((item) => (
                  <span className="badge badge-muted" key={item}>
                    {item}
                  </span>
                ))}
              </div>
            </>
          )}

          {weak.method_note && <small className="muted gap-top">{weak.method_note}</small>}

      <DownloadHistory />
        </>
      )}
    </>
  );
}
