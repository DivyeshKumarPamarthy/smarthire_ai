import React from 'react';

/**
 * Module 10 — one candidate's skills, trend and weak areas, for a recruiter.
 *
 * A filtered view of the same numbers the candidate sees. Two things are
 * withheld by server-side decision, and this component must not reintroduce
 * them from any other source: the practice recommendations and learning
 * resources. Those are coaching addressed to the candidate — a recruiter
 * reading someone's personal remediation plan turns self-improvement advice
 * into a mark against them. The weakness itself is shown as a number, and a
 * number carries its own uncertainty in a way a prescription does not.
 *
 * Nothing from Module 6 appears here either. It is measured in the candidate's
 * own browser, so it is forgeable, and it never feeds a surface that compares
 * people.
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

const pct = (value) => `${Math.max(0, Math.min(100, value ?? 0))}%`;

export default function RecruiterCandidatePerformance({ data, loading, error }) {
  if (loading) return <p className="note">Loading performance…</p>;
  if (error) return <p className="note">Performance could not be loaded for this candidate.</p>;
  if (!data) return null;

  const { skills = [], trend, weak_areas: weak, axis_progress: progress } = data;

  if (!trend || trend.interviews_scored === 0) {
    return (
      <p className="note gap-top">
        No completed interview of theirs has been scored, so there is no performance history to
        show.
      </p>
    );
  }

  const direction = DIRECTION[trend.direction] ?? DIRECTION.insufficient_data;

  return (
    <>
      <p className="label gap-top">Performance</p>
      <div className="row">
        <div>
          <strong>
            {trend.interviews_scored} scored interview
            {trend.interviews_scored === 1 ? '' : 's'}
          </strong>
          <small>
            average {trend.average} · best {trend.best}
            {trend.change !== null && trend.change !== undefined
              ? ` · ${trend.change > 0 ? '+' : ''}${trend.change} between earlier and later halves`
              : ''}
          </small>
        </div>
        <span className={`badge ${direction.tone}`}>{direction.label}</span>
      </div>

      {weak?.available && (
        <>
          <div className="row">
            <div>
              <strong>Weakest axis: {AXIS_LABEL[weak.weakest_axis] ?? weak.weakest_axis}</strong>
              <small>
                {weak.weakest_axis_score} across {weak.graded_answers} graded answer
                {weak.graded_answers === 1 ? '' : 's'} from completed interviews.
              </small>
            </div>
            <span className="badge badge-warn">{weak.weakest_axis_score}</span>
          </div>

          <div className="tags">
            {Object.entries(weak.axis_averages || {}).map(([axis, value]) => (
              <span
                className={`badge ${axis === weak.weakest_axis ? 'badge-warn' : 'badge-muted'}`}
                key={axis}
              >
                {AXIS_LABEL[axis] ?? axis} {value}
              </span>
            ))}
          </div>
        </>
      )}

      {progress?.available && (
        <div className="row gap-top">
          <div>
            <strong>
              {AXIS_LABEL[progress.axis] ?? progress.axis}: {progress.first} → {progress.latest}
            </strong>
            <small>
              across {progress.interviews} completed interview
              {progress.interviews === 1 ? '' : 's'}
            </small>
          </div>
          <span className={`badge ${DIRECTION[progress.direction]?.tone ?? 'badge-muted'}`}>
            {DIRECTION[progress.direction]?.label ?? progress.direction}
          </span>
        </div>
      )}

      {skills.length > 0 && (
        <>
          <p className="label gap-top">By question category</p>
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
                  {Object.entries(skill.axes || {})
                    .map(([axis, value]) => `${AXIS_LABEL[axis] ?? axis} ${value}`)
                    .join(' · ')}
                </small>
              </div>
              <div style={{ minWidth: 140 }}>
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
              it — too thin to read against the others, or against another candidate.
            </small>
          )}
        </>
      )}

      {weak?.method_note && <small className="muted gap-top">{weak.method_note}</small>}
    </>
  );
}
