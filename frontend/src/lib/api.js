/**
 * Thin client for the FastAPI backend.
 *
 * Everything the app knows about the server lives here: the base URL, where the
 * JWT is kept, and how an error response becomes a readable message.
 */

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api').replace(/\/+$/, '');
const TOKEN_KEY = 'smarthire.token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.name = 'ApiError';
    this.status = status; // 0 means the request never reached the server
    this.detail = detail;
  }
}

/**
 * FastAPI sends `detail` as a string for HTTPException, but as a list of
 * {loc, msg} objects for a 422 validation failure — which is what the password
 * rules produce, so it is worth unpacking rather than showing "422".
 */
function readDetail(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => String(item?.msg ?? '').replace(/^Value error,\s*/, ''))
      .filter(Boolean);
    if (messages.length) return messages.join(' ');
  }

  return `Request failed (${status}).`;
}

async function request(path, { method = 'GET', body, auth = false } = {}) {
  const headers = {};

  // FormData must set its own multipart boundary, so do not touch Content-Type
  // and do not stringify it.
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';

  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the API running on port 8000?');
  }

  if (response.status === 204) return null;

  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, readDetail(payload, response.status));
  return payload;
}

const query = (params) => {
  const search = new URLSearchParams(
    Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString();
  return search ? `?${search}` : '';
};

export const api = {
  /* ---------------- auth ---------------- */

  register: ({ name, email, password, role }) =>
    request('/auth/register', { method: 'POST', body: { name, email, password, role } }),

  login: ({ email, password }) =>
    request('/auth/login', { method: 'POST', body: { email, password } }),

  me: () => request('/users/me', { auth: true }),

  /** PUT /users/me. The server has no role field here, so it cannot be escalated. */
  updateProfile: (fields) => request('/users/me', { method: 'PUT', body: fields, auth: true }),

  health: () => request('/health'),

  publicSettings: () => request('/settings/public'),

  /**
   * Google/GitHub sign-in are full page redirects, not fetches: the browser
   * goes to the backend, which bounces it to the provider and back to
   * /login?token=...
   */
  googleLoginUrl: () => `${BASE}/auth/google/login`,
  githubLoginUrl: () => `${BASE}/auth/github/login`,

  /* ---------------- résumés ---------------- */

  uploadResume: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/resumes', { method: 'POST', body: form, auth: true });
  },
  myResume: () => request('/resumes/me', { auth: true }),
  candidateResume: (userId) => request(`/resumes/candidate/${userId}`, { auth: true }),

  /* ---------------- interviews ---------------- */

  generateInterview: (payload) =>
    request('/interviews/generate', { method: 'POST', body: payload, auth: true }),
  listInterviews: (params) => request(`/interviews${query(params)}`, { auth: true }),
  getInterview: (id) => request(`/interviews/${id}`, { auth: true }),
  updateInterview: (id, fields) =>
    request(`/interviews/${id}`, { method: 'PUT', body: fields, auth: true }),
  deleteInterview: (id) => request(`/interviews/${id}`, { method: 'DELETE', auth: true }),
  startInterview: (interviewId) =>
    request('/interviews/start', { method: 'POST', body: { interview_id: interviewId }, auth: true }),
  interviewHistory: (params) => request(`/interviews/history${query(params)}`, { auth: true }),
  domains: () => request('/interviews/domains', { auth: true }),

  /** The voice interviewer is a WebSocket; the token goes in the query string. */
  voiceSocketUrl: (interviewId) => {
    const wsBase = BASE.replace(/^http/, 'ws');
    return `${wsBase}/interviews/voice/${interviewId}?token=${encodeURIComponent(getToken() ?? '')}`;
  },

  /**
   * A recorded answer, as a blob URL playable by an <audio> element.
   *
   * Fetched rather than pointed at directly: the endpoint needs an
   * Authorization header, and <audio src> cannot send one. Callers must
   * URL.revokeObjectURL the result when they are done with it.
   */
  answerAudioUrl: async (interviewId, sequenceNo) => {
    const response = await fetch(
      `${BASE}/interviews/${interviewId}/answers/${sequenceNo}/audio`,
      { headers: { Authorization: `Bearer ${getToken() ?? ''}` } },
    );
    if (!response.ok) throw new ApiError(response.status, 'That recording could not be loaded.');
    return URL.createObjectURL(await response.blob());
  },

  /**
   * Upload the webcam recording for a session.
   *
   * Multipart over HTTP rather than the interview WebSocket: a recording runs
   * to tens of megabytes, and base64 over the socket would inflate it by a
   * third and stall the interview while it transferred.
   */
  uploadRecording: (interviewId, blob, durationSeconds) => {
    const form = new FormData();
    // The server chooses the stored filename; this one is only a label on the
    // multipart part, so it need not be meaningful.
    form.append('file', blob, 'session.webm');
    if (durationSeconds) form.append('duration_seconds', String(durationSeconds));
    return request(`/interviews/${interviewId}/recording`, {
      method: 'POST',
      body: form,
      auth: true,
    });
  },

  /**
   * Module 6: the on-camera tracking measured in this browser during the
   * session. Only these small samples are sent — never a frame of video.
   */
  submitBehavior: (interviewId, body) =>
    request(`/interviews/${interviewId}/behavior`, {
      method: 'POST',
      body,
      auth: true,
    }),

  /** The stored session recording, as a blob URL. Caller must revoke it. */
  recordingUrl: async (interviewId) => {
    const response = await fetch(`${BASE}/interviews/${interviewId}/recording`, {
      headers: { Authorization: `Bearer ${getToken() ?? ''}` },
    });
    if (!response.ok) throw new ApiError(response.status, 'That recording could not be loaded.');
    return URL.createObjectURL(await response.blob());
  },

  /**
   * Module 9: the interview's report as a PDF, downloaded to the browser.
   *
   * Fetched rather than linked, because the endpoint needs the bearer token
   * and a plain <a href> cannot carry one.
   */
  downloadInterviewReport: async (interviewId) => {
    const response = await fetch(
      `${BASE}/notifications/reports/interview/${interviewId}.pdf`,
      { headers: { Authorization: `Bearer ${getToken() ?? ''}` } },
    );
    if (!response.ok) {
      throw new ApiError(response.status, 'That report could not be generated.');
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = `interview-${interviewId}-report.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Revoked on the next tick: revoking immediately can cancel the download
    // in some browsers before it has actually started reading the blob.
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  },

  /* Session control. The live interview drives these over the WebSocket
     instead; these are for controlling a session from outside it. */
  pauseInterview: (id) => request(`/interviews/${id}/pause`, { method: 'POST', auth: true }),
  resumeInterview: (id) => request(`/interviews/${id}/resume`, { method: 'POST', auth: true }),
  endInterview: (id) => request(`/interviews/${id}/end`, { method: 'POST', auth: true }),

  /**
   * Module 5: per-answer communication analysis plus a session roll-up.
   *
   * Sections come back with available=false and a reason when they could not
   * be produced — render the reason rather than treating an absent section as
   * a clean result.
   */
  interviewAnalysis: (interviewId) =>
    request(`/interviews/${interviewId}/analysis`, { auth: true }),

  /* ---------------- analytics ---------------- */

  adminAnalytics: () => request('/analytics/admin', { auth: true }),
  candidateAnalytics: () => request('/analytics/candidate', { auth: true }),
  // Module 8. Separate from the line above because it scans every answer
  // ever given — the dashboard header should not wait on that.
  candidatePerformance: () => request('/analytics/candidate/performance', { auth: true }),

  // --- Module 9: notifications & reports ---
  notifications: (unreadOnly = false) =>
    request(`/notifications?unread_only=${unreadOnly}`, { auth: true }),
  notificationSummary: () => request('/notifications/summary', { auth: true }),
  markNotificationRead: (id) =>
    request(`/notifications/${id}/read`, { method: 'POST', auth: true }),
  markAllNotificationsRead: () =>
    request('/notifications/read-all', { method: 'POST', auth: true }),
  runReminders: (sendEmail = false) =>
    request(`/notifications/reminders/run?send_email=${sendEmail}`, { method: 'POST', auth: true }),
  emailPreference: () => request('/notifications/preferences', { auth: true }),
  setEmailPreference: (enabled) =>
    request('/notifications/preferences', {
      method: 'PUT', auth: true, body: { email_notifications: enabled },
    }),
  stalledDigest: () =>
    request('/notifications/reminders/stalled-digest', { method: 'POST', auth: true }),
  sendPerformanceSummary: (sendEmail = false) =>
    request(`/notifications/performance-summary?send_email=${sendEmail}`, {
      method: 'POST', auth: true,
    }),
  recruiterAnalytics: () => request('/analytics/recruiter', { auth: true }),
  recruiterCandidates: (params) =>
    request(`/analytics/recruiter/candidates${query(params)}`, { auth: true }),
  liveInterviews: () => request('/analytics/live', { auth: true }),
  /**
   * One candidate's completed interviews with score and attention context.
   * Recruiter/admin only; the attention half is filtered server-side.
   */
  candidateInterviews: (userId) =>
    request(`/analytics/recruiter/candidates/${userId}/interviews`, { auth: true }),

  /** Module 5: candidates ranked by their most recently completed interview. */
  leaderboard: (params) => request(`/analytics/leaderboard${query(params)}`, { auth: true }),

  /* ---------------- admin ---------------- */

  listUsers: () => request('/users', { auth: true }),
  directory: (role) => request(`/users/directory${query({ role })}`, { auth: true }),
  setUserRole: (userId, role) =>
    request(`/users/${userId}/role`, { method: 'PUT', body: { role }, auth: true }),
  setUserBlocked: (userId, isBlocked) =>
    request(`/users/${userId}/block`, { method: 'PUT', body: { is_blocked: isBlocked }, auth: true }),

  getSettings: () => request('/settings', { auth: true }),
  updateSettings: (fields) => request('/settings', { method: 'PUT', body: fields, auth: true }),

  metrics: () => request('/metrics', { auth: true }),

  /* ---------------- tickets ---------------- */

  ticketReasons: () => request('/tickets/reasons'),
  createTicket: ({ againstId, reason, details }) =>
    request('/tickets', {
      method: 'POST',
      body: { against_id: againstId, reason, details },
      auth: true,
    }),
  listTickets: (params) => request(`/tickets${query(params)}`, { auth: true }),
  setTicketStatus: (ticketId, status) =>
    request(`/tickets/${ticketId}/status`, { method: 'PUT', body: { status }, auth: true }),
};
