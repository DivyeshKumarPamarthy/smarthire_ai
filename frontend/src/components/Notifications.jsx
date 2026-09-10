import React, { useState } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/useApi';

/**
 * Module 9 — the notification feed, plus the two actions that produce entries
 * in it.
 *
 * The email status of each notification is shown rather than hidden. A
 * candidate who asks for an emailed summary on a deployment with no mail
 * server configured must not be left believing something was sent — "skipped"
 * and "failed" are different facts and both are worth surfacing.
 */

const KIND_LABEL = {
  INTERVIEW_REMINDER: 'Reminder',
  SESSION_ALERT: 'Session alert',
  REPORT_READY: 'Report ready',
  PERFORMANCE_SUMMARY: 'Summary',
};

const EMAIL_NOTE = {
  SENT: { text: 'emailed', tone: 'badge-ok' },
  SKIPPED: { text: 'not emailed — no mail server configured', tone: 'badge-muted' },
  FAILED: { text: 'email failed', tone: 'badge-bad' },
};

const when = (iso) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
};

/**
 * `role` decides which reminder action is offered:
 *
 *   candidate  — their own unfinished interviews, one reminder each
 *   recruiter  — a platform-wide digest, because one entry per candidate
 *                would be unreadable for someone watching everyone
 *   admin      — the same digest, from the same platform-wide query
 */
export default function Notifications({ role = 'candidate' }) {
  const feed = useApi(() => api.notifications());
  const prefs = useApi(() => api.emailPreference());
  const [busy, setBusy] = useState(null);
  const [outcome, setOutcome] = useState(null);

  const run = async (label, action) => {
    setBusy(label);
    setOutcome(null);
    try {
      setOutcome(await action());
      feed.reload();
    } catch (err) {
      setOutcome({ error: err.message });
    } finally {
      setBusy(null);
    }
  };

  const items = feed.data ?? [];
  const unread = items.filter((n) => n.read_at === null).length;

  return (
    <>
      <div className="row">
        <div>
          <strong>
            {items.length} notification{items.length === 1 ? '' : 's'}
          </strong>
          <small>{unread} unread</small>
        </div>
        {unread > 0 && (
          <button
            className="btn"
            disabled={busy !== null}
            onClick={() => run('read', () => api.markAllNotificationsRead())}
          >
            Mark all read
          </button>
        )}
      </div>

      {/* Automated email switch. Shows the deployment's capability as well as
          the user's own setting — someone who turns this on and receives
          nothing is owed the reason. */}
      {prefs.data && (
        <div className="row">
          <div>
            <strong>Automated emails</strong>
            <small>
              {prefs.data.delivery_configured
                ? 'Sent to your address when something is raised for you.'
                : 'No mail server is configured on this deployment, so nothing can be sent yet — this setting takes effect once one is.'}
            </small>
          </div>
          <button
            className={prefs.data.email_notifications ? 'btn btn-primary' : 'btn'}
            disabled={busy !== null}
            onClick={() =>
              run('prefs', async () => {
                await api.setEmailPreference(!prefs.data.email_notifications);
                prefs.reload();
                return {};
              })
            }
          >
            {prefs.data.email_notifications ? 'On' : 'Off'}
          </button>
        </div>
      )}

      <div className="actions gap-top">
        {role === 'candidate' ? (
          <>
            <button
              className="btn"
              disabled={busy !== null}
              onClick={() => run('reminders', () => api.runReminders(false))}
            >
              {busy === 'reminders' ? 'Checking…' : 'Check for unfinished interviews'}
            </button>
            <button
              className="btn"
              disabled={busy !== null}
              onClick={() => run('summary', () => api.sendPerformanceSummary(false))}
            >
              {busy === 'summary' ? 'Building…' : 'Build performance summary'}
            </button>
          </>
        ) : (
          <button
            className="btn"
            disabled={busy !== null}
            onClick={() => run('digest', () => api.stalledDigest())}
          >
            {busy === 'digest' ? 'Checking…' : 'Check for stalled interviews'}
          </button>
        )}
      </div>

      {outcome?.error && <p className="error">{outcome.error}</p>}
      {outcome?.reminders_created !== undefined && (
        <p className="note">
          {outcome.reminders_created === 0
            ? outcome.already_reminded > 0
              ? `Nothing new — you were already reminded about ${outcome.already_reminded} unfinished interview${outcome.already_reminded === 1 ? '' : 's'} recently.`
              : 'No unfinished interviews to remind you about.'
            : `Raised ${outcome.reminders_created} reminder${outcome.reminders_created === 1 ? '' : 's'}${
                outcome.unfinished_interviews > outcome.reminders_created + outcome.already_reminded
                  ? ` — you have ${outcome.unfinished_interviews} unfinished interviews in total, so the rest will follow on a later check.`
                  : '.'
              }`}
        </p>
      )}

      {feed.loading && <p className="note">Loading…</p>}
      {feed.error && <p className="error">Your notifications could not be loaded.</p>}
      {!feed.loading && items.length === 0 && (
        <p className="note">
          {role === 'candidate'
            ? 'Nothing yet. Finishing an interview raises a notification here when its report is ready.'
            : 'Nothing yet. Completed interviews and new reports appear here as they happen.'}
        </p>
      )}

      {items.map((n) => {
        const email = EMAIL_NOTE[n.email_status];
        return (
          <div className="card gap-top" key={n.id}>
            <div className="row">
              <div>
                <strong>{n.title}</strong>
                <small>{when(n.created_at)}</small>
              </div>
              <span className={`badge ${n.read_at === null ? 'badge-warn' : 'badge-muted'}`}>
                {KIND_LABEL[n.kind] ?? n.kind}
              </span>
            </div>

            {/* Bodies are composed server-side with real newlines between
                paragraphs, so they are preserved rather than collapsed. */}
            <p className="note" style={{ whiteSpace: 'pre-wrap' }}>
              {n.body}
            </p>

            <div className="row">
              <div>
                {email && (
                  <span className={`badge ${email.tone}`}>{email.text}</span>
                )}
                {n.email_error && <small className="muted">{n.email_error}</small>}
              </div>
              {n.read_at === null && (
                <button
                  className="btn"
                  disabled={busy !== null}
                  onClick={() => run(`read-${n.id}`, () => api.markNotificationRead(n.id))}
                >
                  Mark read
                </button>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}
