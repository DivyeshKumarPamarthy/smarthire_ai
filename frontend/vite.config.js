import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Reject a VITE_API_URL that cannot work, at build time.
 *
 * Same principle as the JWT startup guard on the backend: the failure this
 * catches is silent. Vite bakes whatever string it is handed into the bundle,
 * so a malformed value builds cleanly, deploys cleanly, and then fails every
 * single API call in the browser with nothing wrong in any log.
 *
 * The specific mistake worth guarding against is easy to make. Render's
 * `fromService` / `property: host` yields a bare private-network hostname —
 * no scheme, not browser-reachable — and it looks entirely reasonable in the
 * dashboard. Pasting just the hostname by hand has the same result.
 *
 * Build time rather than boot time on purpose: this fails the deploy instead
 * of shipping an app that loads and then does nothing.
 */
function assertUsableApiUrl() {
  const raw = process.env.VITE_API_URL;

  // Unset is fine — api.js falls back to http://localhost:8000/api, which is
  // correct for local development and is the only case that should rely on it.
  if (!raw) return;

  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(
      `VITE_API_URL is not a usable URL: ${JSON.stringify(raw)}\n` +
        '  It must be an absolute URL including the scheme, e.g.\n' +
        '    https://smarthire-api.onrender.com/api\n' +
        '  A bare hostname will not work. On Render this usually means\n' +
        "  fromService/property: host was used — that returns the service's\n" +
        '  hostname on the private network, which a browser cannot reach.',
    );
  }

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error(
      `VITE_API_URL must be http or https, got ${JSON.stringify(url.protocol)}`,
    );
  }

  // Not fatal: the prefix is the backend's API_PREFIX setting, so a deployment
  // that changed it is entitled to a different path. But the default is /api,
  // api.js appends paths straight onto this value, and omitting it 404s every
  // request — worth saying out loud rather than discovering in the network tab.
  if (!url.pathname.replace(/\/+$/, '').endsWith('/api')) {
    console.warn(
      `\n[vite] VITE_API_URL is ${raw} — note it does not end in /api.\n` +
        "        The backend serves under API_PREFIX, '/api' by default, and\n" +
        '        api.js appends request paths directly to this value.\n' +
        '        Unless you changed API_PREFIX, every request will 404.\n',
    );
  }
}

assertUsableApiUrl();

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 5453,
    host: true,
  },
});
