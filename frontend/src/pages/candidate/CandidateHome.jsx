import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AppLayout from '../../components/AppLayout';
import Section from '../../components/Section';
import ReportDialog from '../../components/ReportDialog';
import InterviewReview from '../../components/InterviewReview';
import { Panel } from '../../components/Panel';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../lib/api';
import { useApi } from '../../lib/useApi';
import PerformanceAnalytics from '../../components/PerformanceAnalytics';
import { downloadTextFile, buildActivityReport } from '../../lib/report';

const TYPES = ['TECHNICAL', 'HR', 'APTITUDE', 'BEHAVIORAL'];
const LEVELS = ['EASY', 'MEDIUM', 'HARD'];
const MAX_MB = 5;

const STATUS_TONE = {
  CREATED: 'badge-muted',
  IN_PROGRESS: 'badge-bad',
  COMPLETED: 'badge-ok',
  ABANDONED: 'badge-warn',
  OPEN: 'badge-warn',
  RESOLVED: 'badge-ok',
  DISMISSED: 'badge-muted',
};

const initials = (name) =>
  String(name).split(' ').filter(Boolean).map((p) => p[0]).join('').slice(0, 2).toUpperCase();

/**
 * Defined at module scope on purpose. Declaring it inside CandidateHome would
 * make it a new component type on every render, so React would unmount and
 * remount every button on each keystroke in the domain field.
 */
function Picker({ label, items, active, field, onPick }) {
  return (
    <div className="field">
      <span className="label">{label}</span>
      <div className="choices">
        {items.map((value) => (
          <button
            key={value}
            type="button"
            className={value === active ? 'choice on' : 'choice'}
            onClick={() => onPick(field, value)}
          >
            {value.toLowerCase()}
          </button>
        ))}
      </div>
    </div>
  );
}

const shortTime = (iso) => (iso ? new Date(iso).toLocaleString() : '—');

const fileSize = (bytes) =>
  bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;

const duration = (start, end) => {
  if (!start || !end) return '—';
  const mins = Math.round((new Date(end) - new Date(start)) / 60000);
  return mins < 1 ? '<1m' : `${mins}m`;
};

export default function CandidateHome() {
  const navigate = useNavigate();
  const { user, updateProfile } = useAuth();
  const me = user?.name ?? 'Candidate';

  const stats = useApi(() => api.candidateAnalytics());
  // Module 8. Its own request: this walks every answer ever given, and the
  // header above must not wait on that scan to render.
  const performance = useApi(() => api.candidatePerformance());
  const interviews = useApi(() => api.listInterviews({ limit: 50 }));
  const resume = useApi(() => api.myResume());
  const recruiters = useApi(() => api.directory('RECRUITER'));
  const tickets = useApi(() => api.listTickets());

  // résumé upload
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [fileError, setFileError] = useState(null);

  // interview setup
  const [setup, setSetup] = useState({
    interview_type: 'TECHNICAL',
    difficulty: 'MEDIUM',
    domain: 'backend developer',
    question_count: 8,
  });
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState(null);

  const [reportTarget, setReportTarget] = useState(null);
  const [reviewTarget, setReviewTarget] = useState(null);

  const pick = (field, value) => setSetup((prev) => ({ ...prev, [field]: value }));

  // settings
  const [profile, setProfile] = useState({ name: me, password: '' });
  const [profileState, setProfileState] = useState({ saving: false, saved: false, error: null });

  const handleFile = async (f) => {
    if (!f) return;
    // Fast client-side feedback; the server re-checks both of these, and the
    // magic bytes too, because neither check can be trusted from the browser.
    if (f.type !== 'application/pdf') return setFileError('Only PDF files are accepted.');
    if (f.size > MAX_MB * 1024 * 1024)
      return setFileError(`File exceeds the ${MAX_MB} MB limit.`);

    setFileError(null);
    setUploading(true);
    try {
      await api.uploadResume(f);
      resume.reload();
      stats.reload();
    } catch (err) {
      // The server distinguishes "not configured" from "quota reached" from a
      // generic outage — pass its message straight through rather than
      // flattening all three into one guess about the API key.
      setFileError(err.detail ?? 'Upload failed.');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const generate = async (e) => {
    e.preventDefault();
    setGenerateError(null);
    setGenerating(true);
    try {
      const created = await api.generateInterview(setup);
      interviews.reload();
      stats.reload();
      navigate(`/interview/live?interview=${created.id}`);
    } catch (err) {
      setGenerateError(err.detail ?? 'Could not generate the interview.');
    } finally {
      setGenerating(false);
    }
  };

  const s = stats.data;
  const ex = resume.data?.extracted;

  return (
    <AppLayout>
      {/* ---------- overview ---------- */}
      <Section
        id="overview"
        title={`Welcome back, ${me.split(' ')[0]}`}
        subtitle="Your real activity. Scores are not shown because nothing scores interviews yet."
        action={
          <button
            className="btn btn-primary"
            disabled={!s}
            onClick={() =>
              downloadTextFile(
                'smarthire-activity-summary.txt',
                buildActivityReport({
                  candidate: me,
                  email: user?.email,
                  stats: s,
                  interviews: interviews.data ?? [],
                  resume: resume.data,
                })
              )
            }
          >
            Download summary
          </button>
        }
      >
        <Panel {...stats} onRetry={stats.reload}>
          {s && (
            <>
              <div className="grid cols-4">
                <div className="stat">
                  <b>{s.interviews_total}</b>
                  <span>Interviews</span>
                </div>
                <div className="stat">
                  <b>{s.interviews_by_status?.COMPLETED ?? 0}</b>
                  <span>Completed</span>
                </div>
                <div className="stat">
                  <b>
                    {s.questions_answered}/{s.questions_total}
                  </b>
                  <span>Questions answered</span>
                </div>
                <div className="stat">
                  <b>{s.has_resume ? `${s.resume_technologies_count}` : '—'}</b>
                  <span>{s.has_resume ? 'Technologies on résumé' : 'No résumé yet'}</span>
                </div>
              </div>

              <p className="note">
                Last interview: {s.last_interview_at ? shortTime(s.last_interview_at) : 'never'}
              </p>
            </>
          )}
        </Panel>
      </Section>

      {/* ---------- resume ---------- */}
      <Section
        id="resume"
        title="Resume"
        subtitle="Upload a PDF. It is parsed on the server and stored against your account."
      >
        <div className="grid cols-2">
          <div className="card">
            <h2>Upload</h2>
            <div
              className="drop"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                handleFile(e.dataTransfer.files?.[0]);
              }}
            >
              <p>Drop your resume PDF here, or choose a file. Max {MAX_MB} MB.</p>
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf"
                hidden
                onChange={(e) => handleFile(e.target.files?.[0])}
              />
              <button
                className="btn btn-primary"
                disabled={uploading}
                onClick={() => inputRef.current?.click()}
              >
                {uploading ? 'Uploading and parsing…' : 'Browse files'}
              </button>
            </div>

            {uploading && (
              <p className="note">
                Extracting text and reading your résumé — this takes a few seconds.
              </p>
            )}
            {fileError && <p className="error">{fileError}</p>}

            <Panel
              {...resume}
              empty="No resume uploaded yet."
              onRetry={resume.reload}
            >
              {resume.data && (
                <div className="row">
                  <span className="avatar">PDF</span>
                  <div>
                    <strong>{resume.data.filename}</strong>
                    <small>
                      {fileSize(resume.data.size_bytes)} &middot; uploaded{' '}
                      {shortTime(resume.data.uploaded_at)}
                    </small>
                  </div>
                  <span className={`badge ${resume.data.status === 'PARSED' ? 'badge-ok' : 'badge-warn'}`}>
                    {resume.data.status.toLowerCase()}
                  </span>
                </div>
              )}
            </Panel>
          </div>

          <div className="card">
            <h2>Extracted profile</h2>
            <Panel
              {...resume}
              empty="Upload your resume to see the skills, experience and education we read from it."
              onRetry={resume.reload}
            >
              {ex && (
                <>
                  <p className="muted">{ex.summary}</p>

                  <div className="row">
                    <div>
                      <strong>Total experience</strong>
                      <small>
                        {ex.total_experience_years} year
                        {ex.total_experience_years === 1 ? '' : 's'}
                      </small>
                    </div>
                  </div>

                  <p className="label gap-top">Technologies ({ex.technologies.length})</p>
                  <div className="tags">
                    {ex.technologies.map((t) => (
                      <span key={t} className="badge badge-info">
                        {t}
                      </span>
                    ))}
                  </div>

                  <p className="label gap-top">Skills ({ex.skills.length})</p>
                  <div className="tags">
                    {ex.skills.map((t) => (
                      <span key={t} className="badge badge-muted">
                        {t}
                      </span>
                    ))}
                  </div>

                  <p className="label gap-top">Experience</p>
                  {ex.experience.map((role, i) => (
                    <div key={`${role.company}-${i}`} className="row">
                      <div>
                        <strong>
                          {role.role} &middot; {role.company}
                        </strong>
                        <small>
                          {role.start_date} – {role.is_current ? 'Present' : role.end_date}
                        </small>
                      </div>
                    </div>
                  ))}

                  <p className="label gap-top">Education</p>
                  {ex.education.map((edu, i) => (
                    <div key={`${edu.institution}-${i}`} className="row">
                      <div>
                        <strong>
                          {edu.degree}
                          {edu.field_of_study ? `, ${edu.field_of_study}` : ''}
                        </strong>
                        <small>
                          {edu.institution} &middot; {edu.year}
                          {edu.grade ? ` · ${edu.grade}` : ''}
                        </small>
                      </div>
                    </div>
                  ))}
                </>
              )}
            </Panel>
          </div>
        </div>
      </Section>

      {/* ---------- interview ---------- */}
      <Section
        id="interview"
        title="Configure session"
        subtitle="Questions are generated to match the role and level."
      >
        <form className="card" onSubmit={generate}>
          <Picker label="Interview type" items={TYPES} active={setup.interview_type} field="interview_type" onPick={pick} />
          <Picker label="Difficulty" items={LEVELS} active={setup.difficulty} field="difficulty" onPick={pick} />

          <div className="field">
            <label className="label" htmlFor="domain">
              Role or domain
            </label>
            <input
              id="domain"
              value={setup.domain}
              // functional form: spreading the captured `setup` would revert a
              // type/difficulty chosen moments earlier, before React re-rendered
              onChange={(e) => setSetup((prev) => ({ ...prev, domain: e.target.value }))}
              placeholder="backend developer, sales executive, HR…"
            />
            <small className="muted">Any role works — this is a free-text field.</small>
          </div>

          <div className="field">
            <label className="label" htmlFor="count">
              Questions
            </label>
            <input
              id="count"
              type="number"
              min={1}
              max={25}
              value={setup.question_count}
              onChange={(e) =>
                setSetup((prev) => ({ ...prev, question_count: Number(e.target.value) || 1 }))
              }
            />
          </div>

          {generateError && <p className="error">{generateError}</p>}

          <button type="submit" className="btn btn-primary btn-block" disabled={generating}>
            {generating ? 'Generating questions…' : 'Generate and start interview'}
          </button>
        </form>
      </Section>

      {/* ---------- history ---------- */}
      <Section
        id="history"
        title="Interview history"
        subtitle="Every interview you have generated."
      >
        <div className="card">
          <Panel
            {...interviews}
            isEmpty={interviews.data?.length === 0}
            empty="You have not generated an interview yet. Use the section above to create one."
            onRetry={interviews.reload}
          >
            <div className="scroll-x">
              <table className="table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Domain</th>
                    <th>Level</th>
                    <th>Questions</th>
                    <th>Created</th>
                    <th>Duration</th>
                    <th className="num">Score</th>
                    <th>Status</th>
                    <th className="end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {interviews.data?.map((row) => (
                    <tr key={row.id}>
                      <td>{row.interview_type}</td>
                      <td>{row.domain}</td>
                      <td className="num">{row.difficulty.toLowerCase()}</td>
                      <td className="num">{row.question_count}</td>
                      <td className="num">{shortTime(row.created_at)}</td>
                      <td className="num">{duration(row.started_at, row.completed_at)}</td>
                      <td className="num">
                        {row.overall_score != null ? (
                          <span className="mono">
                            {row.overall_score.toFixed(1)} &middot; {row.score_rating}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>
                        <span className={`badge ${STATUS_TONE[row.status]}`}>
                          {row.status.toLowerCase().replace('_', ' ')}
                        </span>
                      </td>
                      <td className="end">
                        {row.status === 'COMPLETED' && (
                          <button className="btn" onClick={() => setReviewTarget(row)}>
                            View
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </Section>

      {/* ---------- analytics ---------- */}
      <Section
        id="analytics"
        title="Analytics"
        subtitle="What the platform can actually measure today."
      >
        <Panel {...stats} onRetry={stats.reload}>
          {s && (
            <div className="card">
              <h2>Interviews by type</h2>
              {Object.keys(s.interviews_by_type ?? {}).length === 0 ? (
                <p className="note">Nothing yet — generate an interview to see this fill in.</p>
              ) : (
                Object.entries(s.interviews_by_type).map(([type, count]) => {
                  const peak = Math.max(...Object.values(s.interviews_by_type));
                  return (
                    <div key={type} className="row">
                      <div>
                        <strong>{type}</strong>
                        <small>
                          {count} interview{count === 1 ? '' : 's'}
                        </small>
                      </div>
                      <div className="meter">
                        <i style={{ width: `${Math.round((count / peak) * 100)}%` }} />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </Panel>

        <div className="card">
          <h2>Performance history</h2>
          <PerformanceAnalytics
            data={performance.data}
            loading={performance.loading}
            error={performance.error}
          />
        </div>

        <div className="grid cols-2">
          <div className="card">
            <h2>Your score</h2>
            {s?.latest_score != null ? (
              <>
                <div className="row">
                  <div>
                    <strong>Most recent</strong>
                    <small>From your latest scored interview</small>
                  </div>
                  <span className={`badge ${STATUS_TONE.COMPLETED}`}>
                    {s.latest_score.toFixed(1)} &middot; {s.latest_score_rating}
                  </span>
                </div>
                {s.best_score != null && (
                  <div className="row">
                    <div>
                      <strong>Best</strong>
                      <small>Across every scored interview</small>
                    </div>
                    <span className="mono">{s.best_score.toFixed(1)}</span>
                  </div>
                )}
              </>
            ) : (
              <p className="note">
                Complete an interview with the microphone answered to see your score here.
              </p>
            )}
          </div>
          <div className="card">
            <h2>How scoring works</h2>
            <p className="muted">
              Each answer is graded 0-100 on four axes — communication (30%), confidence (25%),
              technical relevance (30%) and professionalism (15%) — and averaged across the
              interview. It is an AI assessment against a fixed rubric, not a certified
              evaluation. Open a past interview from History below to see the breakdown per
              question.
            </p>
          </div>
        </div>
      </Section>

      {/* ---------- report ---------- */}
      <Section
        id="report"
        title="Report a recruiter"
        subtitle="Raises a ticket for an administrator to review."
      >
        <div className="card">
          <h2>Recruiters</h2>
          <Panel
            {...recruiters}
            isEmpty={recruiters.data?.length === 0}
            empty="No recruiters are registered yet."
            onRetry={recruiters.reload}
          >
            {recruiters.data?.map((r) => (
              <div key={r.id} className="row">
                <span className="avatar">{initials(r.name)}</span>
                <div>
                  <strong>{r.name}</strong>
                  <small>recruiter</small>
                </div>
                <button className="btn" onClick={() => setReportTarget(r)}>
                  Report
                </button>
              </div>
            ))}
          </Panel>
        </div>

        <div className="card">
          <h2>Reports you have raised</h2>
          <Panel
            {...tickets}
            isEmpty={tickets.data?.length === 0}
            empty="You have not raised any reports."
            onRetry={tickets.reload}
          >
            {tickets.data?.map((ticket) => (
              <div key={ticket.id} className="row">
                <div>
                  <strong>{ticket.against_name}</strong>
                  <small>
                    #{ticket.id} &middot; {ticket.reason} &middot; {shortTime(ticket.created_at)}
                  </small>
                </div>
                <span className={`badge ${STATUS_TONE[ticket.status]}`}>
                  {ticket.status.toLowerCase()}
                </span>
              </div>
            ))}
          </Panel>
        </div>
      </Section>

      {/* ---------- settings ---------- */}
      <Section
        id="settings"
        title="Account settings"
        subtitle="Manage your profile details and password."
      >
        <form
          className="card card-narrow"
          onSubmit={async (e) => {
            e.preventDefault();
            setProfileState({ saving: true, saved: false, error: null });
            try {
              const fields = { name: profile.name };
              if (profile.password) fields.password = profile.password;
              await updateProfile(fields);
              setProfile({ ...profile, password: '' });
              setProfileState({ saving: false, saved: true, error: null });
              setTimeout(() => setProfileState((p) => ({ ...p, saved: false })), 2500);
            } catch (err) {
              setProfileState({ saving: false, saved: false, error: err.detail ?? 'Save failed.' });
            }
          }}
        >
          <h2>Candidate profile</h2>

          <div className="field">
            <label className="label" htmlFor="profile-name">
              Full name
            </label>
            <input
              id="profile-name"
              value={profile.name}
              onChange={(e) => setProfile({ ...profile, name: e.target.value })}
            />
          </div>

          <div className="field">
            <label className="label" htmlFor="profile-email">
              Email
            </label>
            <input id="profile-email" value={user?.email ?? ''} disabled />
            <small className="muted">Your email cannot be changed here.</small>
          </div>

          <div className="field">
            <label className="label" htmlFor="profile-password">
              New password
            </label>
            <input
              id="profile-password"
              type="password"
              placeholder="Leave blank to keep your current password"
              value={profile.password}
              onChange={(e) => setProfile({ ...profile, password: e.target.value })}
            />
          </div>

          {profileState.saved && <p className="note">Settings saved.</p>}
          {profileState.error && <p className="error">{profileState.error}</p>}

          <button type="submit" className="btn btn-primary btn-block" disabled={profileState.saving}>
            {profileState.saving ? 'Saving…' : 'Save changes'}
          </button>
        </form>
      </Section>

      {reportTarget && (
        <ReportDialog
          target={reportTarget.name}
          targetRole="recruiter"
          onCancel={() => setReportTarget(null)}
          onSubmit={async ({ reason, details }) => {
            await api.createTicket({ againstId: reportTarget.id, reason, details });
            setReportTarget(null);
            tickets.reload();
          }}
        />
      )}

      {reviewTarget && (
        <InterviewReview interview={reviewTarget} onClose={() => setReviewTarget(null)} />
      )}
    </AppLayout>
  );
}
