import React from 'react';
import { RATING_TONE } from '../lib/scoring';

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
function TrendChart({ points }) {
  if (points.length < 2) return null;

  const W = 640;
  const H = 120;
  const PAD = 8;
  const scores = points.map((p) => p.score);
  const lo = Math.min(...scores, 0);
  const hi = Math.max(...scores, 100);
  const span = hi - lo || 1;

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

export default function PerformanceAnalytics({ data, loading, error }) {
  if (loading) return <p className="note">Loading your performance history…</p>;
  if (error) return <p className="error">Your performance history could not be loaded.</p>;
  if (!data) return null;

  const { skills = [], trend, weak_areas: weak } = data;
  const direction = DIRECTION[trend?.direction] ?? DIRECTION.insufficient_data;
  const hasScores = (trend?.interviews_scored ?? 0) > 0;

  if (!hasScores) {
    return (
      <p className="note">
        No interview of yours has been scored yet. Finish an interview to start building a
        history here — skills, trend and weak areas all read from your scored answers.
      </p>
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
                {weak.graded_answers} graded answer{weak.graded_answers === 1 ? '' : 's'}.
              </small>
            </div>
            <span className="badge badge-warn">{weak.weakest_axis_score}</span>
          </div>

          {weak.weakest_category && (
            <div className="row">
              <div>
                <strong>{weak.weakest_category}</strong>
                <small>Your lowest-scoring question category with enough answers to judge.</small>
              </div>
              <span className="badge badge-warn">{weak.weakest_category_score}</span>
            </div>
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
        </>
      )}
    </>
  );
}
