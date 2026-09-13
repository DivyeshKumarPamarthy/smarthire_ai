import React from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { Panel } from './Panel';

/**
 * Module 10 — candidates worth a closer look, each with its reason attached.
 *
 * Every insight shows the figures that produced it. That is not decoration: a
 * recruiter who cannot check why an insight fired should not be shown it, and
 * the rule is enforced server-side too — an insight with no evidence is never
 * emitted.
 *
 * Deliberately not a ranking and not a recommendation. Insights are listed in
 * candidate order, never ordered by strength, and nothing here suggests a
 * hiring decision. This platform scores mock interviews with an AI that can be
 * wrong; it can say someone is worth a look and why, and that is the limit of
 * what the data supports.
 */

const KIND = {
  consistently_strong: { label: 'Scoring well', tone: 'badge-ok' },
  improving: { label: 'Improving', tone: 'badge-ok' },
  strong_in_skill: { label: 'Skill strength', tone: 'badge-ok' },
  thin_evidence: { label: 'Too early to read', tone: 'badge-muted' },
};

export default function ShortlistInsights() {
  const insights = useApi(() => api.shortlistInsights());
  const data = insights.data;

  return (
    <div className="card">
      <h2>Shortlisting insights</h2>
      <p className="muted">
        Patterns worth a closer look, drawn from completed interviews. Each one shows the
        figures behind it so you can check it.
      </p>

      <Panel {...insights} onRetry={insights.reload}>
        {data && (
          <>
            <div className="row">
              <div>
                <strong>
                  {data.insights.length} insight{data.insights.length === 1 ? '' : 's'}
                </strong>
                <small>
                  {data.scored_candidates} candidate
                  {data.scored_candidates === 1 ? '' : 's'} with scored interviews
                  {data.pool_average !== null && data.pool_average !== undefined
                    ? ` · pool average ${data.pool_average}`
                    : ''}
                </small>
              </div>
            </div>

            {data.insights.length === 0 ? (
              <p className="note gap-top">
                Nothing stands out yet. That is a normal result — these rules only fire on
                clear patterns, and inventing something to say about every candidate would
                make this panel noise rather than signal.
              </p>
            ) : (
              data.insights.map((insight, i) => {
                const kind = KIND[insight.kind] ?? { label: insight.kind, tone: 'badge-muted' };
                return (
                  <div className="row" key={`${insight.candidate_id}-${insight.kind}-${i}`}>
                    <div>
                      <strong>
                        {insight.headline}
                        {insight.provisional && (
                          <span className="badge badge-muted" style={{ marginLeft: 8 }}>
                            provisional
                          </span>
                        )}
                      </strong>
                      {/* The evidence is the point. Never collapse or truncate
                          it — an insight a recruiter cannot verify should not
                          be on screen. */}
                      <small>{insight.evidence}</small>
                    </div>
                    <span className={`badge ${kind.tone}`}>{kind.label}</span>
                  </div>
                );
              })
            )}

            <small className="muted gap-top">{data.note}</small>
          </>
        )}
      </Panel>
    </div>
  );
}
