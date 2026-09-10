import React, { useState } from 'react';
import AppLayout from '../../components/AppLayout';
import Section from '../../components/Section';
import Notifications from '../../components/Notifications';
import { Panel } from '../../components/Panel';
import Leaderboard from '../../components/Leaderboard';
import { api } from '../../lib/api';
import { useApi } from '../../lib/useApi';

const STATUS_TONE = { OPEN: 'badge-warn', RESOLVED: 'badge-ok', DISMISSED: 'badge-muted' };
const ROLES = ['CANDIDATE', 'RECRUITER', 'ADMIN'];

const initials = (name) =>
  String(name).split(' ').filter(Boolean).map((p) => p[0]).join('').slice(0, 2).toUpperCase();

const shortTime = (iso) => (iso ? new Date(iso).toLocaleString() : '—');

export default function AdminHome() {
  const stats = useApi(() => api.adminAnalytics());
  const users = useApi(() => api.listUsers());
  const metrics = useApi(() => api.metrics());
  const settings = useApi(() => api.getSettings());
  const health = useApi(() => api.health());

  const [ticketFilter, setTicketFilter] = useState('OPEN');
  const tickets = useApi(
    () => api.listTickets(ticketFilter === 'ALL' ? {} : { status: ticketFilter }),
    [ticketFilter]
  );

  const [busy, setBusy] = useState(null);
  const [actionError, setActionError] = useState(null);

  const [form, setForm] = useState(null);
  const [saved, setSaved] = useState(false);
  // seed the editable copy once settings arrive
  if (settings.data && form === null) {
    setForm({
      max_questions: settings.data.max_questions,
      session_minutes: settings.data.session_minutes,
      open_signup: settings.data.open_signup,
      maintenance: settings.data.maintenance,
    });
  }

  const run = async (key, fn, reload) => {
    setBusy(key);
    setActionError(null);
    try {
      await fn();
      reload();
    } catch (err) {
      setActionError(err.detail ?? 'Action failed.');
    } finally {
      setBusy(null);
    }
  };

  const s = stats.data;

  return (
    <AppLayout>
      {/* ---------- overview ---------- */}
      <Section
        id="overview"
        title="Platform overview"
        subtitle="Live counts from the database."
      >
        <Panel {...stats} onRetry={stats.reload}>
          {s && (
            <>
              <div className="grid cols-4">
                <div className="stat">
                  <b>{s.users_total}</b>
                  <span>Total users</span>
                </div>
                <div className="stat">
                  <b>{s.users_by_role.RECRUITER ?? 0}</b>
                  <span>Recruiters</span>
                </div>
                <div className="stat">
                  <b>{s.interviews_total}</b>
                  <span>Interviews</span>
                </div>
                <div className="stat">
                  <b>{s.resumes_total}</b>
                  <span>Résumés</span>
                </div>
              </div>

              <div className="grid cols-5">
                <div className="stat">
                  <b>{s.users_by_role.CANDIDATE ?? 0}</b>
                  <span>Candidates</span>
                </div>
                <div className="stat">
                  <b>{s.users_blocked}</b>
                  <span>Blocked</span>
                </div>
                <div className="stat">
                  <b>
                    {s.questions_answered}/{s.questions_total}
                  </b>
                  <span>Questions answered</span>
                </div>
                <div className="stat">
                  <b>{s.tickets_open}</b>
                  <span>Open tickets</span>
                </div>
                <div className="stat">
                  <b>{s.average_score != null ? s.average_score.toFixed(1) : '—'}</b>
                  <span>Avg. score ({s.scored_interviews} scored)</span>
                </div>
              </div>

              <div className="card">
                <h2>Interviews created (last 14 days)</h2>
                <div className="chart">
                  {s.interviews_last_14_days.map((point) => {
                    const peak = Math.max(1, ...s.interviews_last_14_days.map((p) => p.count));
                    return (
                      <div key={point.date} title={`${point.date} — ${point.count}`}>
                        <i style={{ height: `${Math.round((point.count / peak) * 90)}px` }} />
                        <span>{point.date.slice(5)}</span>
                      </div>
                    );
                  })}
                </div>
                <p className="note">
                  {s.interviews_last_14_days.reduce((a, p) => a + p.count, 0)} interviews created in
                  this window.
                </p>
              </div>

              <div className="card">
                <h2>Breakdown</h2>
                <div className="row">
                  <div>
                    <strong>By status</strong>
                    <small>{JSON.stringify(s.interviews_by_status)}</small>
                  </div>
                </div>
                <div className="row">
                  <div>
                    <strong>By type</strong>
                    <small>{JSON.stringify(s.interviews_by_type)}</small>
                  </div>
                </div>
                <div className="row">
                  <div>
                    <strong>Résumés by parse status</strong>
                    <small>{JSON.stringify(s.resumes_by_status)}</small>
                  </div>
                </div>
              </div>
            </>
          )}
        </Panel>
      </Section>

      {/* ---------- users ---------- */}
      <Section
        id="users"
        title="Manage users"
        subtitle="Real accounts. Change a role or block an account — both take effect immediately."
      >
        {actionError && <p className="error">{actionError}</p>}

        <div className="card">
          <Panel {...users} isEmpty={users.data?.length === 0} empty="No accounts yet." onRetry={users.reload}>
            <div className="scroll-x">
              <table className="table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th className="end">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {users.data?.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <div className="cell">
                          <span className="avatar">{initials(user.name)}</span>
                          {user.name}
                        </div>
                      </td>
                      <td className="num">{user.email}</td>
                      <td>
                        <select
                          aria-label={`Role for ${user.name}`}
                          value={user.role}
                          disabled={busy === `role-${user.id}`}
                          onChange={(e) =>
                            run(
                              `role-${user.id}`,
                              () => api.setUserRole(user.id, e.target.value),
                              () => {
                                users.reload();
                                stats.reload();
                              }
                            )
                          }
                        >
                          {ROLES.map((role) => (
                            <option key={role} value={role}>
                              {role.toLowerCase()}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <span className={`badge ${user.is_blocked ? 'badge-bad' : 'badge-ok'}`}>
                          {user.is_blocked ? 'Blocked' : 'Active'}
                        </span>
                      </td>
                      <td className="end">
                        <button
                          className="btn"
                          disabled={busy === `block-${user.id}`}
                          onClick={() =>
                            run(
                              `block-${user.id}`,
                              () => api.setUserBlocked(user.id, !user.is_blocked),
                              () => {
                                users.reload();
                                stats.reload();
                              }
                            )
                          }
                        >
                          {busy === `block-${user.id}`
                            ? '…'
                            : user.is_blocked
                              ? 'Unblock'
                              : 'Block'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </Section>

      {/* ---------- leaderboard ---------- */}
      <Section
        id="leaderboard"
        title="Leaderboard"
        subtitle="Candidates ranked by their most recently completed interview."
      >
        <Leaderboard />
      </Section>

      {/* ---------- tickets ---------- */}
      <Section
        id="tickets"
        title="Report tickets"
        subtitle="Reports raised by candidates and recruiters, stored server-side."
      >
        <div className="card">
          <h2>Filter</h2>
          <div className="choices">
            {['OPEN', 'RESOLVED', 'DISMISSED', 'ALL'].map((value) => (
              <button
                key={value}
                type="button"
                className={value === ticketFilter ? 'choice on' : 'choice'}
                onClick={() => setTicketFilter(value)}
              >
                {value.toLowerCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          <h2>
            {ticketFilter === 'ALL' ? 'All tickets' : `${ticketFilter.toLowerCase()} tickets`}
            {tickets.data ? ` (${tickets.data.length})` : ''}
          </h2>

          <Panel
            {...tickets}
            isEmpty={tickets.data?.length === 0}
            empty={`No ${ticketFilter === 'ALL' ? '' : ticketFilter.toLowerCase()} tickets. Raise one from a candidate or recruiter account to see it here.`}
            onRetry={tickets.reload}
          >
            {tickets.data?.map((ticket) => (
              <div key={ticket.id} className="row">
                <div>
                  <strong>
                    {ticket.reporter_name} ({ticket.reporter_role.toLowerCase()}) reported{' '}
                    {ticket.against_name} ({ticket.against_role.toLowerCase()})
                  </strong>
                  <small>
                    #{ticket.id} &middot; {ticket.reason} &middot; {shortTime(ticket.created_at)}
                  </small>
                  {ticket.details && <p className="muted">{ticket.details}</p>}
                </div>
                <span className={`badge ${STATUS_TONE[ticket.status]}`}>
                  {ticket.status.toLowerCase()}
                </span>
                {ticket.status === 'OPEN' && (
                  <div className="actions">
                    <button
                      className="btn"
                      disabled={busy === `t-${ticket.id}`}
                      onClick={() =>
                        run(
                          `t-${ticket.id}`,
                          () => api.setTicketStatus(ticket.id, 'DISMISSED'),
                          () => {
                            tickets.reload();
                            stats.reload();
                          }
                        )
                      }
                    >
                      Dismiss
                    </button>
                    <button
                      className="btn btn-primary"
                      disabled={busy === `t-${ticket.id}`}
                      onClick={() =>
                        run(
                          `t-${ticket.id}`,
                          () => api.setTicketStatus(ticket.id, 'RESOLVED'),
                          () => {
                            tickets.reload();
                            stats.reload();
                          }
                        )
                      }
                    >
                      Resolve
                    </button>
                  </div>
                )}
              </div>
            ))}
          </Panel>
        </div>
      </Section>

      {/* ---------- api telemetry ---------- */}
      <Section
        id="api"
        title="API usage & latency"
        subtitle="Measured by the server's own timing middleware."
      >
        <Panel {...metrics} onRetry={metrics.reload}>
          {metrics.data && (
            <>
              <div className="grid cols-4">
                <div className="stat">
                  <b>{metrics.data.total_requests.toLocaleString()}</b>
                  <span>Requests</span>
                </div>
                <div className="stat">
                  <b>{metrics.data.avg_latency_ms} ms</b>
                  <span>Avg latency</span>
                </div>
                <div className="stat">
                  <b>{metrics.data.p95_latency_ms} ms</b>
                  <span>p95 latency</span>
                </div>
                <div className="stat">
                  <b>{metrics.data.error_rate}%</b>
                  <span>Error rate</span>
                </div>
              </div>

              <p className="note">
                Counters are in-process and reset when the server restarts — these are totals since{' '}
                {shortTime(metrics.data.window_start)}, not all-time figures.{' '}
                <button className="btn" onClick={metrics.reload}>
                  Refresh
                </button>
              </p>

              <div className="card">
                <h2>Busiest endpoints</h2>
                {metrics.data.endpoints.length === 0 ? (
                  <p className="note">No requests recorded yet.</p>
                ) : (
                  <div className="scroll-x">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Endpoint</th>
                          <th>Requests</th>
                          <th>Avg</th>
                          <th>Max</th>
                          <th className="end">Errors</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.data.endpoints.slice(0, 12).map((row) => (
                          <tr key={row.endpoint}>
                            <td className="num">{row.endpoint}</td>
                            <td className="num">{row.requests.toLocaleString()}</td>
                            <td className="num">{row.avg_ms} ms</td>
                            <td className="num">{row.max_ms} ms</td>
                            <td className="end">
                              <span
                                className={`badge ${
                                  row.error_rate === 0
                                    ? 'badge-ok'
                                    : row.error_rate < 5
                                      ? 'badge-warn'
                                      : 'badge-bad'
                                }`}
                              >
                                {row.error_rate}%
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </Panel>
      </Section>

      {/* ---------- activity ---------- */}
      <Section
        id="activity"
        title="System activity"
        subtitle="Audit log of configuration changes and account actions."
      >
        <div className="card">
          <h2>Audit log</h2>
          <p className="note">
            <span className="badge badge-muted">Not yet available</span>
          </p>
          <p className="muted">
            Nothing records administrator actions yet, so there is no log to show. The previous
            entries here were placeholders. Ticket resolutions are recorded and visible in the
            Tickets section above.
          </p>
        </div>
      </Section>

      {/* ---------- ai ---------- */}
      <Section
        id="ai"
        title="AI configuration"
        subtitle="Which provider and models are actually serving requests."
      >
        <Panel {...health} onRetry={health.reload}>
          {health.data && (
            <div className="card card-narrow">
              <div className="row">
                <div>
                  <strong>Provider</strong>
                  <small className="mono">{health.data.ai?.provider ?? 'unknown'}</small>
                </div>
                <span className={`badge ${health.data.ai?.reachable ? 'badge-ok' : 'badge-bad'}`}>
                  {health.data.ai?.reachable ? 'reachable' : (health.data.ai?.detail ?? 'unreachable')}
                </span>
              </div>
              <div className="row">
                <div>
                  <strong>Generation &amp; résumé model</strong>
                  <small className="mono">{health.data.ai_model}</small>
                </div>
              </div>
              <p className="muted gap-top">
                These are read-only. The provider and model are set server-side in{' '}
                <span className="mono">.env</span> (<span className="mono">AI_PROVIDER</span>,{' '}
                <span className="mono">OLLAMA_MODEL</span> / <span className="mono">GEMINI_MODEL</span>)
                so the running configuration cannot drift from what this page claims. If the
                provider is unreachable, interview generation falls back to the built-in question
                bank and résumé parsing returns 503. Spoken answers are recorded and stored as
                audio — no speech model is involved.
              </p>
            </div>
          )}
        </Panel>
      </Section>

      {/* ---------- settings ---------- */}
      <Section
        id="alerts"
        title="Alerts"
        subtitle="Interview activity and reminders raised for you."
      >
        <div className="card">
          <Notifications role="admin" />
        </div>
      </Section>

      <Section
        id="settings"
        title="Platform settings"
        subtitle="Stored server-side. Every setting here is enforced by the API."
      >
        <Panel {...settings} onRetry={settings.reload}>
          {form && (
            <form
              className="card card-narrow"
              onSubmit={async (e) => {
                e.preventDefault();
                setActionError(null);
                setBusy('settings');
                try {
                  await api.updateSettings(form);
                  settings.reload();
                  setSaved(true);
                  setTimeout(() => setSaved(false), 2500);
                } catch (err) {
                  setActionError(err.detail ?? 'Could not save settings.');
                } finally {
                  setBusy(null);
                }
              }}
            >
              <h2>Session limits</h2>

              <div className="field">
                <label className="label" htmlFor="max-questions">
                  Max questions per session
                </label>
                <input
                  id="max-questions"
                  type="number"
                  min={1}
                  max={25}
                  value={form.max_questions}
                  onChange={(e) =>
                    setForm({ ...form, max_questions: Number(e.target.value) || 1 })
                  }
                />
                <small className="muted">Rejects larger requests to /interviews/generate.</small>
              </div>

              <div className="field">
                <label className="label" htmlFor="session-minutes">
                  Session time limit (minutes)
                </label>
                <input
                  id="session-minutes"
                  type="number"
                  min={1}
                  max={180}
                  value={form.session_minutes}
                  onChange={(e) =>
                    setForm({ ...form, session_minutes: Number(e.target.value) || 1 })
                  }
                />
                <small className="muted">Drives the countdown in the live interview.</small>
              </div>

              <label className="check">
                <input
                  type="checkbox"
                  checked={form.open_signup}
                  onChange={(e) => setForm({ ...form, open_signup: e.target.checked })}
                />
                Allow public sign-up
              </label>

              <label className="check">
                <input
                  type="checkbox"
                  checked={form.maintenance}
                  onChange={(e) => setForm({ ...form, maintenance: e.target.checked })}
                />
                Maintenance mode (non-admin API calls return 503)
              </label>

              {saved && <p className="note">Settings saved.</p>}
              {actionError && <p className="error">{actionError}</p>}

              <button
                type="submit"
                className="btn btn-primary btn-block"
                disabled={busy === 'settings'}
              >
                {busy === 'settings' ? 'Saving…' : 'Save settings'}
              </button>
            </form>
          )}
        </Panel>
      </Section>
    </AppLayout>
  );
}
